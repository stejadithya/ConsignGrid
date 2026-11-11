"""Stocktakes (stock checks) at reseller locations.

A Sales Rep records and submits the count (P-018). Lines without a shortage need no decision. When tyres are short,
the shortage stock is held (blocked) and the dealer has STOCKTAKE_FIND_DAYS (5) to find them (release 1.11, D3):
found → the dealer asks for a re-check and staff start a re-count; disagree → a dispute for the WM/RM; otherwise the
tyres are invoiced as sold (a confirmed sale, a replacement and an invoice record), by the dealer, by staff on their
behalf, or automatically when the window ends. Nothing is written off as "missing" (finding 28). Reminders go out
daily during the window. The legacy SUBMITTED → classify/approve path for counts from before P-018 is unchanged.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.numbering import next_number
from app.core.permissions import P, Role, role_has
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.inventory.models import StockBalance, TxnType
from app.modules.inventory.service import Ledger, Ref, lock_balances, system_location
from app.modules.invoicing import service as invoicing
from app.modules.notifications.service import notify_users, reseller_users, staff_in_roles
from app.modules.sales import service as sales
from app.modules.sales.models import SaleSource
from app.modules.stocktakes.models import Stocktake, StocktakeLine, StocktakeStatus

NOT_FOUND_RULE = "In consignment, tyres that aren't found are re-checked or invoiced."


@dataclass
class CountInput:
    product_id: int
    counted_qty: int
    counted_damaged_qty: int = 0
    notes: str | None = None


def _get(db: Session, stocktake_id: int, lock: bool = False) -> Stocktake:
    stmt = select(Stocktake).where(Stocktake.id == stocktake_id).options(selectinload(Stocktake.lines))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    st = db.execute(stmt).scalar_one_or_none()
    if st is None:
        raise NotFoundError("Stocktake not found")
    return st


def get_stocktake(db: Session, user: User, stocktake_id: int) -> Stocktake:
    st = _get(db, stocktake_id)
    ensure_reseller_access(user, st.reseller_id, "Stocktake")
    return st


def _validate_counts(counts: list[CountInput]) -> None:
    if len({c.product_id for c in counts}) != len(counts):
        raise BusinessRuleError("Each product may appear only once")
    for c in counts:
        if c.counted_qty < 0 or c.counted_damaged_qty < 0 or c.counted_damaged_qty > c.counted_qty:
            raise BusinessRuleError("Counts must be ≥ 0 and damaged ≤ counted")


def create(db: Session, actor: User, *, location_id: int, count_date: date, counts: list[CountInput],
           notes: str | None = None) -> Stocktake:
    loc = db.get(Location, location_id)
    if loc is None or loc.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError("Stocktakes are for dealer consignment locations")
    if count_date > date.today():
        raise BusinessRuleError("Count date cannot be in the future")
    _validate_counts(counts)
    st = Stocktake(number=next_number(db, "STK"), location_id=loc.id, reseller_id=loc.reseller_id,
                   count_date=count_date, counted_by_user_id=actor.id, status=StocktakeStatus.DRAFT, notes=notes)
    for c in counts:
        if db.get(Product, c.product_id) is None:
            raise NotFoundError(f"Product {c.product_id} not found")
        st.lines.append(StocktakeLine(product_id=c.product_id, counted_qty=c.counted_qty,
                                      counted_damaged_qty=c.counted_damaged_qty, notes=c.notes))
    db.add(st)
    db.flush()
    record_audit(db, actor_id=actor.id, action="stocktake.create", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id, summary=f"Started {st.number} at {loc.code}")
    return st


def update_counts(db: Session, actor: User, stocktake_id: int, counts: list[CountInput]) -> Stocktake:
    st = _get(db, stocktake_id, lock=True)
    if st.status != StocktakeStatus.DRAFT:
        raise ConflictError(f"{st.number} is {st.status}; counts can only change while in draft")
    _validate_counts(counts)
    by_product = {ln.product_id: ln for ln in st.lines}
    for c in counts:
        ln = by_product.get(c.product_id)
        if ln is None:
            if db.get(Product, c.product_id) is None:
                raise NotFoundError(f"Product {c.product_id} not found")
            st.lines.append(StocktakeLine(product_id=c.product_id, counted_qty=c.counted_qty,
                                          counted_damaged_qty=c.counted_damaged_qty, notes=c.notes))
        else:
            ln.counted_qty, ln.counted_damaged_qty, ln.notes = c.counted_qty, c.counted_damaged_qty, c.notes
    db.flush()
    return st


def submit(db: Session, actor: User, stocktake_id: int) -> Stocktake:
    """Snapshot expected balances. SKUs in stock but not counted are added with a count of zero (full count)."""
    st = _get(db, stocktake_id, lock=True)
    if st.status != StocktakeStatus.DRAFT:
        raise ConflictError(f"{st.number} is {st.status}")
    balances = {b.product_id: b for b in db.execute(
        select(StockBalance).where(StockBalance.location_id == st.location_id)).scalars()}
    counted = {ln.product_id for ln in st.lines}
    for pid, b in balances.items():
        if b.on_hand > 0 and pid not in counted:
            st.lines.append(StocktakeLine(product_id=pid, counted_qty=0, counted_damaged_qty=0,
                                          notes="Not counted — added at submission"))
    db.flush()
    for ln in st.lines:
        b = balances.get(ln.product_id)
        ln.expected_qty = b.on_hand if b else 0
        ln.expected_blocked_qty = b.blocked if b else 0
        ln.qty_sold = ln.qty_missing = 0
    st.submitted_at = datetime.now(UTC)
    db.flush()
    record_audit(db, actor_id=actor.id, action="stocktake.submit", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id,
                 summary=f"Submitted {st.number}: {sum(1 for ln in st.lines if ln.variance)} line(s) with variance")
    loc = db.get(Location, st.location_id)
    short = [ln for ln in st.lines if ln.shortage]
    if not short:
        # Nothing for the reseller to decide: post surpluses and damaged-stock changes straight away.
        _post(db, st, loc, actor)
        _finish(st, actor)
        return st
    # Hold the shortage so it cannot be sold or transferred while the reseller decides.
    hold = Ledger(db, TxnType.STOCKTAKE_ADJUSTMENT, actor_id=actor.id, ref=Ref("stocktake", st.id, st.number),
                  reason=f"Held pending dealer confirmation of stock check {st.number}")
    for ln in short:
        bal = lock_balances(db, [(loc.id, ln.product_id)])[(loc.id, ln.product_id)]
        ln.qty_held = max(0, min(ln.shortage, bal.available))
        if ln.qty_held:
            hold.block(loc, ln.product_id, ln.qty_held)
    st.status = StocktakeStatus.AWAITING_RESELLER
    days = get_settings().stocktake_find_days
    st.confirm_due_at = st.submitted_at + timedelta(days=days)
    db.flush()
    units = sum(ln.shortage for ln in short)
    reseller = db.get(Reseller, st.reseller_id)
    notify_users(db, [*reseller_users(db, st.reseller_id), reseller.sales_rep_user_id],
                 f"Stock check {st.number}: {units} tyre(s) not found",
                 find_window_text(units, days, st.confirm_due_at) + f" ({reseller.business_name}, {loc.name})",
                 link=_link(st), entity_type="stocktake", entity_id=st.id, exclude=actor.id)
    return st


def find_window_text(units: int, days: int, due: datetime) -> str:
    """What the dealer is told when tyres are not found at a stock check (D3)."""
    return (f"{units} tyre(s) weren't found at today's stock check. You have {days} days to find them. If you find "
            f"them, ask for a re-check. If not, they'll be invoiced as sold on {due:%d %b %Y}.")


def _link(st: Stocktake) -> str:
    return f"/stocktakes/{st.id}"


def _finish(st: Stocktake, actor: User | None) -> None:
    st.status = StocktakeStatus.APPROVED
    st.approved_by_user_id = actor.id if actor else None
    st.approved_at = datetime.now(UTC)


def classify(db: Session, actor: User, stocktake_id: int, line_id: int, *, qty_sold: int, qty_missing: int,
             notes: str | None = None) -> Stocktake:
    st = _get(db, stocktake_id, lock=True)
    if st.status != StocktakeStatus.SUBMITTED:
        raise ConflictError(f"{st.number} is {st.status}")
    ln = next((x for x in st.lines if x.id == line_id), None)
    if ln is None:
        raise NotFoundError("Stocktake line not found")
    if qty_sold < 0 or qty_missing < 0 or qty_sold + qty_missing != ln.shortage:
        raise BusinessRuleError(f"Sold + missing must equal the shortage of {ln.shortage}")
    ln.qty_sold, ln.qty_missing = qty_sold, qty_missing
    if notes:
        ln.notes = notes
    db.flush()
    return st


def approve(db: Session, actor: User, stocktake_id: int) -> Stocktake:
    """Post the approved outcome: sales, loss/gain adjustments and damaged-stock blocks."""
    st = _get(db, stocktake_id, lock=True)
    if st.status != StocktakeStatus.SUBMITTED:
        raise ConflictError(f"{st.number} is {st.status}")
    loc = db.get(Location, st.location_id)
    lock_balances(db, [(loc.id, ln.product_id) for ln in st.lines])
    for ln in st.lines:
        b = db.get(StockBalance, (loc.id, ln.product_id))
        on_hand, blocked = (b.on_hand, b.blocked) if b else (0, 0)
        if on_hand != ln.expected_qty or blocked != ln.expected_blocked_qty:
            raise ConflictError(f"Stock for product {ln.product_id} changed since the count was submitted; recount")
        if ln.qty_sold + ln.qty_missing != ln.shortage:
            raise BusinessRuleError("Every shortage must be classified as sold or missing before approval")

    _post(db, st, loc, actor)
    _finish(st, actor)
    db.flush()
    record_audit(db, actor_id=actor.id, action="stocktake.approve", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id,
                 summary=f"Approved {st.number}: sold {sum(ln.qty_sold for ln in st.lines)}, missing "
                         f"{sum(ln.qty_missing for ln in st.lines)}, surplus "
                         f"{sum(max(0, ln.variance or 0) for ln in st.lines)}")
    return st


def _post(db: Session, st: Stocktake, loc: Location, actor: User | None):
    """Post the outcome: sales for sold quantities, losses for missing, gains for surpluses, damaged-stock blocks.
    actor None: posted by TyreGrow itself (automatic invoicing at the end of the find window)."""
    ref = Ref("stocktake", st.id, st.number)
    adj = system_location(db, LocationType.ADJUSTMENT)
    actor_id = actor.id if actor else None
    ledger = Ledger(db, TxnType.STOCKTAKE_ADJUSTMENT, actor_id=actor_id, approved_by_id=actor_id, ref=ref,
                    reason=f"Stocktake {st.number} approved")
    sale = None
    # 1. Release blocks that are no longer damaged, so stock can be classified.
    for ln in st.lines:
        if ln.counted_damaged_qty < ln.expected_blocked_qty:
            ledger.unblock(loc, ln.product_id, ln.expected_blocked_qty - ln.counted_damaged_qty)
    # 2. Sold quantities become a confirmed sale (chargeable, triggers replenishment).
    sold_lines = [sales.SaleLineInput(product_id=ln.product_id, quantity=ln.qty_sold) for ln in st.lines if ln.qty_sold]
    if sold_lines:
        sale = sales.record_sale(db, actor, location_id=loc.id, sale_date=st.count_date, source=SaleSource.STOCKTAKE,
                                 lines=sold_lines, source_reference=st.number, stocktake_id=st.id,
                                 notes=f"Sales confirmed by stocktake {st.number}")
        st.sale_id = sale.id
    # 3. Unexplained shortages are approved losses; surpluses are approved gains.
    for ln in st.lines:
        if ln.qty_missing:
            ledger.move(ln.product_id, loc, adj, ln.qty_missing)
        if ln.variance and ln.variance > 0:
            ledger.move(ln.product_id, adj, loc, ln.variance)
    # 4. Block newly damaged stock.
    for ln in st.lines:
        if ln.counted_damaged_qty > ln.expected_blocked_qty:
            ledger.block(loc, ln.product_id, ln.counted_damaged_qty - ln.expected_blocked_qty)
    return sale


@dataclass
class Classification:
    line_id: int
    qty_sold: int
    qty_missing: int


# Open checks whose shortage can still be resolved by invoicing it (the find window may be paused).
RESOLVABLE = (StocktakeStatus.AWAITING_RESELLER, StocktakeStatus.RECHECK_REQUESTED, StocktakeStatus.DISPUTED)


def confirm(db: Session, actor: User | None, stocktake_id: int, decisions: list[Classification], *,
            notes: str | None = None, on_behalf_reason: str | None = None) -> Stocktake:
    """Invoice the tyres not found as sold: the dealer, staff on the dealer's behalf (with a reason), or — actor None —
    TyreGrow automatically at the end of the find window."""
    st = _get(db, stocktake_id, lock=True)
    if actor is not None:
        ensure_reseller_access(actor, st.reseller_id, "Stocktake")
    if st.status not in RESOLVABLE:
        raise ConflictError(f"{st.number} is {st.status}; only stock checks awaiting the dealer can be confirmed")
    if actor is None:
        pass   # automatic invoicing; the reason is set by the caller
    elif actor.is_reseller_user:
        if not role_has(actor.role, P.STOCKTAKE_CONFIRM):
            raise PermissionDeniedError("Missing permission: stocktake.confirm")
    else:
        if not role_has(actor.role, P.STOCKTAKE_APPROVE):
            raise PermissionDeniedError("Only the dealer, or a Relationship / Warehouse Manager on their behalf, "
                                        "can confirm a stock check")
        if not on_behalf_reason or len(on_behalf_reason.strip()) < 3:
            raise BusinessRuleError("Give the reason for confirming on the dealer's behalf")
    if any(d.qty_missing > 0 for d in decisions):
        # Release 1.11 (finding 28): nothing is written off as "missing" from a dealer's stock check. The legacy
        # SUBMITTED → classify/approve path for counts from before P-018 is unchanged.
        raise BusinessRuleError(NOT_FOUND_RULE)
    given = {d.line_id: d for d in decisions}
    short = {ln.id: ln for ln in st.lines if ln.shortage}
    if set(given) - set(short):
        raise BusinessRuleError("Only lines with a shortage are confirmed")
    if set(short) - set(given):
        raise BusinessRuleError("Confirm every shortage as sold or missing")
    for line_id, ln in short.items():
        d = given[line_id]
        if d.qty_sold < 0 or d.qty_missing < 0 or d.qty_sold + d.qty_missing != ln.shortage:
            raise BusinessRuleError(f"Sold + missing must equal the shortage of {ln.shortage} for every line")
        ln.qty_sold, ln.qty_missing = d.qty_sold, d.qty_missing

    actor_id = actor.id if actor else None
    loc = db.get(Location, st.location_id)
    lock_balances(db, [(loc.id, ln.product_id) for ln in st.lines])
    release = Ledger(db, TxnType.STOCKTAKE_ADJUSTMENT, actor_id=actor_id, ref=Ref("stocktake", st.id, st.number),
                     reason=f"Release hold: stock check {st.number} confirmed")
    for ln in st.lines:
        if ln.qty_held:
            release.unblock(loc, ln.product_id, ln.qty_held)
            ln.qty_held = 0
    sale = _post(db, st, loc, actor)
    invoice = None
    if sale is not None:
        db.flush()
        db.refresh(sale)
        invoice = invoicing.create_invoice(db, actor, reseller_id=st.reseller_id,
                                           sale_line_ids=[ln.id for ln in sale.lines],
                                           notes=f"Tyres invoiced as sold at stock check {st.number}")
        st.invoice_id = invoice.id
    _finish(st, actor)
    if actor is None or not actor.is_reseller_user:
        st.confirmed_on_behalf_reason = (on_behalf_reason or "").strip() or None
    if notes:
        st.notes = f"{st.notes}\n{notes}" if st.notes else notes
    db.flush()
    sold = sum(ln.qty_sold for ln in st.lines)
    who = ("TyreGrow automatically" if actor is None else
           "the dealer" if actor.is_reseller_user else f"{actor.full_name} on the dealer's behalf")
    record_audit(db, actor_id=actor_id, action="stocktake.confirm", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id,
                 summary=(f"{st.confirmed_on_behalf_reason}: {st.number}" if actor is None else
                          f"Confirmed {st.number} by {who}")
                         + f": {sold} invoiced as sold" + (f"; invoice record {invoice.number}" if invoice else "")
                         + (f" (reason: {st.confirmed_on_behalf_reason})"
                            if st.confirmed_on_behalf_reason and actor is not None else ""))
    reseller = db.get(Reseller, st.reseller_id)
    if actor is None:
        notify_users(db, [*reseller_users(db, st.reseller_id), reseller.sales_rep_user_id,
                          *staff_in_roles(db, Role.RELATIONSHIP_MANAGER)],
                     f"Stock check {st.number}: tyres invoiced",
                     f"{st.confirmed_on_behalf_reason}. {sold} tyre(s) for {reseller.business_name} were invoiced as "
                     "sold" + (f" (invoice record {invoice.number})" if invoice else "") + "; replacements were raised.",
                     link=_link(st), entity_type="stocktake", entity_id=st.id)
    else:
        notify_users(db, [st.counted_by_user_id, reseller.sales_rep_user_id,
                          *staff_in_roles(db, Role.RELATIONSHIP_MANAGER, Role.WAREHOUSE_MANAGER)],
                     f"Stock check {st.number} confirmed",
                     f"{reseller.business_name}: {sold} tyre(s) invoiced as sold"
                     + (f" (invoice record {invoice.number})" if invoice else "") + f" — confirmed by {who}.",
                     link=_link(st), entity_type="stocktake", entity_id=st.id, exclude=actor_id)
    return st


def _all_sold(st: Stocktake) -> list[Classification]:
    return [Classification(ln.id, ln.shortage, 0) for ln in st.lines if ln.shortage]


def auto_invoice_due(db: Session, now: datetime | None = None) -> int:
    """Invoice as sold the tyres not found within the find window (D3). Safe to call often and concurrently: the
    conditional UPDATE claims each due check once (a concurrent caller waits on the row, then no longer matches),
    and a paused check (re-check requested, disputed) is never touched. Returns how many were invoiced."""
    now = now or datetime.now(UTC)
    claimed = db.execute(
        update(Stocktake)
        .where(Stocktake.status == StocktakeStatus.AWAITING_RESELLER, Stocktake.confirm_due_at <= now)
        .values(last_reminded_at=now)
        .returning(Stocktake.id)
    ).scalars().all()
    days = get_settings().stocktake_find_days
    done = 0
    for st_id in claimed:
        try:
            with db.begin_nested():   # one failing check (e.g. a closed dealer) never blocks the others
                st = _get(db, st_id)
                confirm(db, None, st_id, _all_sold(st),
                        on_behalf_reason=f"Automatically invoiced: not found within {days} days")
            done += 1
        except (BusinessRuleError, ConflictError, NotFoundError):
            continue
    return done


def request_recheck(db: Session, actor: User, stocktake_id: int, note: str | None) -> Stocktake:
    """The dealer found the tyres: ask for a re-check. The find window pauses."""
    st = _dealer_action(db, actor, stocktake_id)
    st.status = StocktakeStatus.RECHECK_REQUESTED
    st.recheck_requested_at, st.recheck_requested_by_user_id = datetime.now(UTC), actor.id
    st.recheck_note = (note or "").strip() or None
    db.flush()
    reseller = db.get(Reseller, st.reseller_id)
    tail = f": {st.recheck_note}" if st.recheck_note else ""
    record_audit(db, actor_id=actor.id, action="stocktake.recheck_request", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id, summary=f"{reseller.business_name} asked for a re-check of {st.number}{tail}")
    notify_users(db, [reseller.sales_rep_user_id, *staff_in_roles(db, Role.WAREHOUSE_MANAGER)],
                 f"Re-check requested: {st.number}",
                 f"{reseller.business_name} found the tyres and asked for a re-count{tail}", link=_link(st),
                 entity_type="stocktake", entity_id=st.id, exclude=actor.id)
    return st


def dispute(db: Session, actor: User, stocktake_id: int, message: str) -> Stocktake:
    """The dealer disagrees with the count. The find window pauses; the WM and RM follow up."""
    st = _dealer_action(db, actor, stocktake_id)
    st.status = StocktakeStatus.DISPUTED
    st.disputed_at, st.disputed_by_user_id, st.dispute_note = datetime.now(UTC), actor.id, message.strip()
    db.flush()
    reseller = db.get(Reseller, st.reseller_id)
    record_audit(db, actor_id=actor.id, action="stocktake.dispute", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id, summary=f"{reseller.business_name} disputed {st.number}: {st.dispute_note}")
    notify_users(db, staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER),
                 f"Stock check disputed: {st.number}", f"{reseller.business_name}: {st.dispute_note}",
                 link=_link(st), entity_type="stocktake", entity_id=st.id, exclude=actor.id)
    return st


def _dealer_action(db: Session, actor: User, stocktake_id: int) -> Stocktake:
    st = _get(db, stocktake_id, lock=True)
    ensure_reseller_access(actor, st.reseller_id, "Stocktake")
    if not actor.is_reseller_user or not role_has(actor.role, P.STOCKTAKE_CONFIRM):
        raise PermissionDeniedError("Only the dealer can do this")
    if st.status != StocktakeStatus.AWAITING_RESELLER:
        raise ConflictError(f"{st.number} is {st.status}; only stock checks waiting for the dealer")
    return st


def start_recount(db: Session, actor: User, stocktake_id: int) -> Stocktake:
    """Release the hold, mark the check SUPERSEDED and start a new draft for the same shop with the shortage SKUs."""
    old = _get(db, stocktake_id, lock=True)
    if old.status not in RESOLVABLE:
        raise ConflictError(f"{old.number} is {old.status}; a re-count starts from a check waiting for the dealer")
    loc = db.get(Location, old.location_id)
    held = [ln for ln in old.lines if ln.qty_held]
    if held:
        release = Ledger(db, TxnType.STOCKTAKE_ADJUSTMENT, actor_id=actor.id, ref=Ref("stocktake", old.id, old.number),
                         reason=f"Release hold: stock check {old.number} is being re-counted")
        for ln in held:
            release.unblock(loc, ln.product_id, ln.qty_held)
            ln.qty_held = 0
    old.status = StocktakeStatus.SUPERSEDED
    new = Stocktake(number=next_number(db, "STK"), location_id=old.location_id, reseller_id=old.reseller_id,
                    count_date=date.today(), counted_by_user_id=actor.id, status=StocktakeStatus.DRAFT,
                    recount_of_id=old.id, notes=f"Re-count of {old.number}")
    for ln in old.lines:
        if ln.shortage:
            new.lines.append(StocktakeLine(product_id=ln.product_id, counted_qty=ln.counted_qty,
                                           counted_damaged_qty=ln.counted_damaged_qty,
                                           notes=f"Re-count: {ln.shortage} not found at {old.number}"))
    db.add(new)
    db.flush()
    record_audit(db, actor_id=actor.id, action="stocktake.recount", entity_type="stocktake", entity_id=old.id,
                 reseller_id=old.reseller_id, summary=f"{old.number} superseded by re-count {new.number}")
    notify_users(db, [*reseller_users(db, old.reseller_id), db.get(Reseller, old.reseller_id).sales_rep_user_id],
                 f"Re-count started: {new.number}", f"{old.number} is being re-counted by {actor.full_name}; the tyres "
                 "it held are free again.", link=_link(new), entity_type="stocktake", entity_id=new.id,
                 exclude=actor.id)
    return new


def contacts(db: Session, st: Stocktake) -> list[dict]:
    """Who the dealer can call about a stock check: the warehouse, the Relationship Managers and their sales rep."""
    reseller = db.get(Reseller, st.reseller_id)
    people = [(u, "Warehouse Manager") for u in db.execute(select(User).where(
        User.role == Role.WAREHOUSE_MANAGER, User.is_active.is_(True)).order_by(User.full_name)).scalars()]
    people += [(u, "Relationship Manager") for u in db.execute(select(User).where(
        User.role == Role.RELATIONSHIP_MANAGER, User.is_active.is_(True)).order_by(User.full_name)).scalars()]
    rep = db.get(User, reseller.sales_rep_user_id) if reseller and reseller.sales_rep_user_id else None
    if rep is not None and rep.is_active:
        people.append((rep, "Your sales rep"))
    return [{"role": role, "name": u.full_name, "email": u.email, "phone": u.phone} for u, role in people]


def overdue(st: Stocktake, now: datetime | None = None) -> bool:
    return (st.status == StocktakeStatus.AWAITING_RESELLER and st.confirm_due_at is not None
            and st.confirm_due_at <= (now or datetime.now(UTC)))


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Daily reminders during the find window to the dealer, the sales rep and whoever counted (D3).

    Repeats every STOCKTAKE_REMINDER_HOURS until the tyres are found, disputed or invoiced. Safe to call often and
    concurrently: the conditional UPDATE claims each reminder once. The end of the window is auto_invoice_due's.
    """
    now = now or datetime.now(UTC)
    interval = timedelta(hours=get_settings().stocktake_reminder_hours)
    claimed = db.execute(
        update(Stocktake)
        .where(Stocktake.status == StocktakeStatus.AWAITING_RESELLER, Stocktake.confirm_due_at > now,
               or_(Stocktake.last_reminded_at <= now - interval,
                   (Stocktake.last_reminded_at.is_(None)) & (Stocktake.submitted_at <= now - interval)))
        .values(last_reminded_at=now, reminder_count=Stocktake.reminder_count + 1)
        .returning(Stocktake.id)
    ).scalars().all()
    for st_id in claimed:
        st = _get(db, st_id)
        reseller = db.get(Reseller, st.reseller_id)
        loc = db.get(Location, st.location_id)
        units = sum(ln.shortage for ln in st.lines)
        notify_users(db, [*reseller_users(db, st.reseller_id), st.counted_by_user_id, reseller.sales_rep_user_id],
                     f"Reminder: {units} tyre(s) not found at stock check {st.number}",
                     f"{reseller.business_name} ({loc.name}): find them and ask for a re-check, or they'll be invoiced "
                     f"as sold on {st.confirm_due_at:%d %b %Y}.",
                     link=_link(st), entity_type="stocktake", entity_id=st.id)
    return len(claimed)


def awaiting_confirmation(db: Session, user: User) -> list[Stocktake]:
    stmt = (select(Stocktake).options(selectinload(Stocktake.lines))
            .where(Stocktake.status.in_([x.value for x in RESOLVABLE])).order_by(Stocktake.confirm_due_at))
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Stocktake.reseller_id == restricted)
    return list(db.execute(stmt).scalars())


def cancel(db: Session, actor: User, stocktake_id: int, reason: str) -> Stocktake:
    st = _get(db, stocktake_id, lock=True)
    if st.status not in (StocktakeStatus.DRAFT, StocktakeStatus.SUBMITTED, *RESOLVABLE):
        raise ConflictError(f"{st.number} is {st.status}")
    held = [ln for ln in st.lines if ln.qty_held]
    if held:
        loc = db.get(Location, st.location_id)
        release = Ledger(db, TxnType.STOCKTAKE_ADJUSTMENT, actor_id=actor.id, ref=Ref("stocktake", st.id, st.number),
                         reason=f"Release hold: stock check {st.number} cancelled")
        for ln in held:
            release.unblock(loc, ln.product_id, ln.qty_held)
            ln.qty_held = 0
    st.status = StocktakeStatus.CANCELLED
    record_audit(db, actor_id=actor.id, action="stocktake.cancel", entity_type="stocktake", entity_id=st.id,
                 reseller_id=st.reseller_id, summary=f"Cancelled {st.number}: {reason}")
    return st


def list_stocktakes(db: Session, user: User, *, reseller_id: int | None = None, location_id: int | None = None,
                    status: StocktakeStatus | None = None) -> list[Stocktake]:
    stmt = select(Stocktake).options(selectinload(Stocktake.lines))
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Stocktake.reseller_id == restricted)
    if reseller_id is not None:
        stmt = stmt.where(Stocktake.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(Stocktake.location_id == location_id)
    if status is not None:
        stmt = stmt.where(Stocktake.status == status)
    return list(db.execute(stmt.order_by(Stocktake.id.desc())).scalars())
