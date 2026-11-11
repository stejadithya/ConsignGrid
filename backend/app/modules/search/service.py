"""One search box across the app (global search, option B).

Documents by number (and the Xero invoice number for those allowed to see it), dealers, tyres and people, a few of
each. Everyone only finds what they could already open: each group needs the permission its screen needs, and a
dealer user finds only their own documents, never another dealer, warehouse documents or staff.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import P, role_has
from app.modules.catalogue.models import Product
from app.modules.catalogue.service import _compact as compact
from app.modules.catalogue.service import _search_fields as tyre_fields
from app.modules.catalogue.service import search_tokens
from app.modules.customers.models import Location, Reseller
from app.modules.identity.models import User
from app.modules.inventory.models import InventoryTransaction
from app.modules.invoicing.models import Invoice
from app.modules.purchasing.models import GoodsReceipt, PurchaseOrder
from app.modules.replenishment.models import Delivery, ReplenishmentRequest
from app.modules.sales.models import ConsignmentSale
from app.modules.stock_requests.models import StockRequest
from app.modules.stocktakes.models import Stocktake
from app.modules.transfers.models import Transfer

MIN_CHARS = 3
PER_GROUP = 5


@dataclass
class Hit:
    type: str          # e.g. STOCK_REQUEST, DEALER, TYRE, PERSON
    label: str         # what it is, in words ("Stock request")
    id: int
    title: str         # the number, dealer name, tyre name or person's name
    subtitle: str | None
    status: str | None
    when: date | datetime | None
    href: str
    exact: bool = False   # the query is this document's number: Enter opens it


@dataclass
class Results:
    query: str
    documents: list[Hit] = field(default_factory=list)
    dealers: list[Hit] = field(default_factory=list)
    tyres: list[Hit] = field(default_factory=list)
    people: list[Hit] = field(default_factory=list)


def _key(text: str) -> str:
    """What a number or name looks like without case or punctuation ("srq 2" → "srq2")."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _number_match(column, key: str):
    """Number contains what was typed; "SRQ-2", "srq 000002" and "000002" all find SRQ-000002."""
    digits = key.lstrip("abcdefghijklmnopqrstuvwxyz")
    letters = key[: len(key) - len(digits)]
    conds = [compact(column).like(f"%{key}%")]
    if letters and digits:   # "srq2" → prefix srq and number ending in 2 when padded ("SRQ-000002")
        conds.append(compact(column).like(f"{letters}%{digits}"))
    return or_(*conds)


def _exact(number: str, key: str) -> bool:
    k = _key(number)
    if k == key:
        return True
    digits = key.lstrip("abcdefghijklmnopqrstuvwxyz")
    letters = key[: len(key) - len(digits)]
    return bool(letters and digits) and k.startswith(letters) and k[len(letters):].lstrip("0") == digits.lstrip("0")


def _dealer_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(Reseller.id, Reseller.business_name).where(Reseller.id.in_(ids))).all()) if ids else {}


def _documents(db: Session, user: User, key: str) -> list[Hit]:
    own = user.reseller_id if user.is_reseller_user else None
    can = lambda perm: role_has(user.role, perm)   # noqa: E731
    hits: list[Hit] = []

    def add(rows, make):
        for r in rows:
            hits.append(make(r))

    def scoped(model, q):
        return q.where(model.reseller_id == own) if own else q

    if can(P.STOCK_REQUEST_READ):
        rows = db.execute(scoped(StockRequest, select(StockRequest).where(_number_match(StockRequest.number, key)))
                          .order_by(StockRequest.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})
        add(rows, lambda r: Hit("STOCK_REQUEST", "Stock request", r.id, r.number, names.get(r.reseller_id),
                                r.status, r.created_at, f"/stock-requests/{r.id}", _exact(r.number, key)))
    if can(P.REPLENISHMENT_READ):
        rows = db.execute(scoped(ReplenishmentRequest, select(ReplenishmentRequest)
                                 .where(_number_match(ReplenishmentRequest.number, key)))
                          .order_by(ReplenishmentRequest.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})
        add(rows, lambda r: Hit("REPLENISHMENT", "Replenishment request", r.id, r.number, names.get(r.reseller_id),
                                r.status, r.created_at, f"/replenishment/{r.id}", _exact(r.number, key)))
        rows = db.execute(scoped(Delivery, select(Delivery).where(_number_match(Delivery.number, key)))
                          .order_by(Delivery.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})
        add(rows, lambda r: Hit("DELIVERY", "Delivery", r.id, r.number, names.get(r.reseller_id), r.status,
                                r.dispatched_at, f"/stock-requests/{r.stock_request_id}" if r.stock_request_id
                                else f"/replenishment?tab=deliveries&q={r.number}", _exact(r.number, key)))
    if can(P.TRANSFER_READ):
        q = select(Transfer).where(_number_match(Transfer.number, key))
        if own:
            q = q.where(or_(Transfer.destination_reseller_id == own, Transfer.source_reseller_id == own))
        rows = db.execute(q.order_by(Transfer.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.destination_reseller_id for r in rows} | {r.source_reseller_id for r in rows})

        def transfer_hit(t: Transfer) -> Hit:
            if own:   # a dealer sees their own side only; the other dealer is never named
                sub = "Coming to you" if t.destination_reseller_id == own else "Going to another dealer"
            else:
                sub = f"{names.get(t.source_reseller_id, 'Source not chosen')} → {names.get(t.destination_reseller_id, '')}"
            return Hit("TRANSFER", "Transfer", t.id, t.number, sub, t.status, t.requested_at, f"/transfers/{t.id}",
                       _exact(t.number, key))
        add(rows, transfer_hit)
    if can(P.INVENTORY_READ):
        rows = db.execute(scoped(ConsignmentSale, select(ConsignmentSale).where(_number_match(ConsignmentSale.number, key)))
                          .order_by(ConsignmentSale.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})
        add(rows, lambda r: Hit("SALE", "Sale", r.id, r.number, names.get(r.reseller_id), None, r.sale_date,
                                f"/sales?sale={r.id}", _exact(r.number, key)))
        rows = db.execute(scoped(Stocktake, select(Stocktake).where(_number_match(Stocktake.number, key)))
                          .order_by(Stocktake.id.desc()).limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})
        add(rows, lambda r: Hit("STOCKTAKE", "Stock check", r.id, r.number, names.get(r.reseller_id), r.status,
                                r.count_date, f"/stocktakes/{r.id}", _exact(r.number, key)))
        if not own:   # stock movements are the warehouse's ledger
            rows = db.execute(select(InventoryTransaction).where(_number_match(InventoryTransaction.number, key))
                              .order_by(InventoryTransaction.id.desc()).limit(PER_GROUP)).scalars().all()
            add(rows, lambda r: Hit("MOVEMENT", "Stock movement", r.id, r.number,
                                    r.txn_type.value.replace("_", " ").capitalize(), None, r.occurred_at,
                                    f"/inventory/movement?number={r.number}", _exact(r.number, key)))
    if can(P.INVOICE_READ):
        xero = can(P.INVOICE_REFERENCE_READ) and not own
        cond = _number_match(Invoice.number, key)
        if xero:
            cond = or_(cond, compact(func.coalesce(Invoice.external_reference, "")).like(f"%{key}%"))
        rows = db.execute(scoped(Invoice, select(Invoice).where(cond)).order_by(Invoice.id.desc())
                          .limit(PER_GROUP)).scalars().all()
        names = _dealer_names(db, {r.reseller_id for r in rows})

        def invoice_hit(r: Invoice) -> Hit:
            sub = names.get(r.reseller_id)
            if xero and r.external_reference:
                sub = f"{sub} · Xero {r.external_reference}"
            return Hit("INVOICE", "Invoice record", r.id, r.number, sub, r.status, r.created_at, f"/invoices/{r.id}",
                       _exact(r.number, key) or (xero and _key(r.external_reference or "") == key))
        add(rows, invoice_hit)
    if can(P.PURCHASING_MANAGE) and not own:
        rows = db.execute(select(PurchaseOrder).where(or_(
            _number_match(PurchaseOrder.number, key),
            compact(func.coalesce(PurchaseOrder.supplier_reference, "")).like(f"%{key}%")))
            .order_by(PurchaseOrder.id.desc()).limit(PER_GROUP)).scalars().all()
        add(rows, lambda r: Hit("PURCHASE_ORDER", "Purchase order", r.id, r.number, r.supplier_name, r.status,
                                r.created_at, f"/purchasing?q={r.number}", _exact(r.number, key)))
        rows = db.execute(select(GoodsReceipt).where(_number_match(GoodsReceipt.number, key))
                          .order_by(GoodsReceipt.id.desc()).limit(PER_GROUP)).scalars().all()
        add(rows, lambda r: Hit("RECEIPT", "Goods receipt", r.id, r.number, r.supplier_reference, None,
                                r.received_at, f"/purchasing?tab=receipts&q={r.number}", _exact(r.number, key)))
    # Exact matches first, then newest.
    hits.sort(key=lambda h: (not h.exact, -(h.when.timestamp() if isinstance(h.when, datetime)
                                             else datetime.combine(h.when, datetime.min.time()).timestamp()
                                             if isinstance(h.when, date) else 0)))
    return hits[: PER_GROUP * 2]


def _dealers(db: Session, user: User, query: str) -> list[Hit]:
    if user.is_reseller_user or not role_has(user.role, P.RESELLER_READ):
        return []
    q = select(Reseller)
    for token in search_tokens(query):
        like = f"%{token}%"
        shops = select(Location.reseller_id).where(or_(compact(Location.name).like(like),
                                                       compact(func.coalesce(Location.city, "")).like(like),
                                                       compact(Location.code).like(like)))
        q = q.where(or_(*(compact(func.coalesce(c, "")).like(like) for c in (
            Reseller.business_name, Reseller.trading_name, Reseller.account_ref, Reseller.contact_name,
            Reseller.phone, Reseller.email)), Reseller.id.in_(shops)))
    rows = db.execute(q.order_by(Reseller.business_name).limit(PER_GROUP)).scalars().all()
    return [Hit("DEALER", "Dealer", r.id, r.business_name,
                " · ".join(x for x in (r.account_ref, r.contact_name, r.phone) if x), r.status, None,
                f"/resellers/{r.id}") for r in rows]


def _tyres(db: Session, user: User, query: str) -> list[Hit]:
    if not role_has(user.role, P.CATALOGUE_READ):
        return []
    q = select(Product).where(Product.is_active.is_(True))
    for token in search_tokens(query):
        q = q.where(or_(*(compact(cast(f, String)).like(f"%{token}%") for f in tyre_fields())))
    rows = db.execute(q.order_by(Product.sku).limit(PER_GROUP)).scalars().all()
    return [Hit("TYRE", "Tyre", p.id, p.display_name, p.sku, None, None,
                f"/products/{p.id}" if not user.is_reseller_user else f"/consignment?sku={p.sku}") for p in rows]


def _people(db: Session, user: User, query: str) -> list[Hit]:
    if not role_has(user.role, P.USER_MANAGE):
        return []
    q = select(User)
    for token in search_tokens(query):
        q = q.where(or_(compact(User.full_name).like(f"%{token}%"), compact(User.email).like(f"%{token}%")))
    rows = db.execute(q.order_by(User.full_name).limit(PER_GROUP)).scalars().all()
    return [Hit("PERSON", "Person", u.id, u.full_name, u.email,
                "LOCKED" if u.locked_until and u.locked_until > datetime.now(u.locked_until.tzinfo)
                else ("ACTIVE" if u.is_active else "INACTIVE"), None, f"/admin?q={u.email}") for u in rows]


def search(db: Session, user: User, query: str) -> Results:
    query = (query or "").strip()
    key = _key(query)
    out = Results(query=query)
    if len(key) < MIN_CHARS:
        return out
    out.documents = _documents(db, user, key)
    out.dealers = _dealers(db, user, query)
    out.tyres = _tyres(db, user, query)
    out.people = _people(db, user, query)
    return out
