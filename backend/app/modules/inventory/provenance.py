"""Where a tyre at a location came from: a short, plain-language summary for the ⓘ next to each SKU.

Read-only and computed from records that already exist (the ledger, deliveries, requests). It is fetched on demand
for one location + tyre, so it costs nothing on page load. A fixed handful of small indexed queries per call.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.industry import vocab
from app.core.lookups import by_id
from app.core.permissions import ROLE_LABELS, Role
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access
from app.modules.inventory.models import Bucket, InventoryEntry, InventoryTransaction, StockBalance, TxnType
from app.modules.replenishment.models import Delivery, DeliveryLine, ReplenishmentReason, ReplenishmentRequest
from app.modules.sales.models import ConsignmentSale, SaleSource
from app.modules.stock_requests.models import StockRequest
from app.modules.stocktakes.models import Stocktake
from app.modules.transfers.models import Transfer

LOOKBACK_DAYS = 365
MAX_ENTRIES = 60     # arrivals read from the ledger (newest first)
MAX_SHOWN = 20       # arrivals returned for "show all"


def provenance(db: Session, viewer: User, location_id: int, product_id: int) -> dict:
    loc = db.get(Location, location_id)
    if loc is None:
        raise NotFoundError("Location not found")
    ensure_reseller_access(viewer, loc.reseller_id, "Location")
    dealer_view = viewer.is_reseller_user

    bal = db.get(StockBalance, (location_id, product_id))
    on_hand = bal.on_hand if bal else 0

    # 1. Arrivals: stock added to this location's on-hand quantity, newest first.
    since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    rows = db.execute(
        select(InventoryEntry.quantity, InventoryTransaction)
        .join(InventoryTransaction, InventoryTransaction.id == InventoryEntry.transaction_id)
        .where(InventoryEntry.location_id == location_id, InventoryEntry.product_id == product_id,
               InventoryEntry.bucket == Bucket.ON_HAND, InventoryEntry.quantity > 0,
               InventoryTransaction.occurred_at >= since)
        .order_by(InventoryTransaction.occurred_at.desc(), InventoryTransaction.id.desc())
        .limit(MAX_ENTRIES)
    ).tuples().all()

    # 2. Batch-load the documents behind them (one query per kind, only when needed).
    refs: dict[str, set[int]] = defaultdict(set)
    for _, t in rows:
        if t.reference_type and t.reference_id is not None:
            refs[t.reference_type].add(t.reference_id)
    deliveries = by_id(db, Delivery, refs["delivery"])
    lines_by_delivery: dict[int, list[DeliveryLine]] = defaultdict(list)
    if deliveries:
        for ln in db.execute(select(DeliveryLine).where(DeliveryLine.delivery_id.in_(deliveries),
                                                        DeliveryLine.product_id == product_id)
                             .order_by(DeliveryLine.id)).scalars():
            lines_by_delivery[ln.delivery_id].append(ln)
    requests = by_id(db, ReplenishmentRequest, {ln.request_id for lns in lines_by_delivery.values() for ln in lns})
    origin_ids: dict[str, set[int]] = defaultdict(set)
    for r in requests.values():
        if r.origin_type and r.origin_id is not None:
            origin_ids[r.origin_type].add(r.origin_id)
    stock_requests = by_id(db, StockRequest, origin_ids["stock_request"])
    sales = by_id(db, ConsignmentSale, origin_ids["consignment_sale"] | refs["consignment_sale"])
    stocktakes = by_id(db, Stocktake, refs["stocktake"] | {s.stocktake_id for s in sales.values() if s.stocktake_id})
    transfers = by_id(db, Transfer, refs["transfer"])
    users = by_id(db, User, {t.actor_user_id for _, t in rows}
                  | {r.created_by_user_id for r in requests.values()}
                  | {s.created_by_user_id for s in stock_requests.values()})
    other_dealers = by_id(db, Reseller, set() if dealer_view else {t.source_reseller_id for t in transfers.values()})

    your = "your" if dealer_view else f"the {vocab.partner}'s"

    def who(uid: int | None) -> str | None:
        u = users.get(uid)
        if u is None:
            return None
        if dealer_view and u.reseller_id == viewer.reseller_id:
            return "you"
        return f"{u.full_name} ({ROLE_LABELS[Role(u.role)]})"

    def ordered(uid: int | None, number: str | None, first: bool) -> str:
        by = who(uid)
        ref = f" ({number})" if number else ""
        if by == "you":
            return f"Latest stock: a new {vocab.item} you ordered{ref}" if first else f"You ordered this{ref}"
        lead = f"Latest stock: a new {vocab.item} ordered by" if first else "Ordered by"
        return f"{lead} {by}{ref}" if by else f"{lead.removesuffix(' by')}{ref}"

    def for_request(req: ReplenishmentRequest) -> tuple[str, str]:
        """(reason, group) for stock delivered against a request."""
        if req.reason == ReplenishmentReason.SALE:
            sale = sales.get(req.origin_id) if req.origin_type == "consignment_sale" else None
            if sale is not None and sale.source == SaleSource.STOCKTAKE:
                st = stocktakes.get(sale.stocktake_id)
                return (f"Replacement for {vocab.items} sold, found at stock check {st.number if st else ''}".rstrip(),
                        "replacing sales")
            return f"Replacement for {your} sale {req.origin_number or ''}".rstrip(), "replacing sales"
        if req.reason == ReplenishmentReason.STOCK_REQUEST:
            sr = stock_requests.get(req.origin_id)
            return (ordered(sr.created_by_user_id if sr else req.created_by_user_id, req.origin_number,
                            req.first_supply), "Latest stock" if req.first_supply else "ordered")
        if req.reason == ReplenishmentReason.MANUAL:
            return (ordered(req.created_by_user_id, req.number, req.first_supply),
                    "Latest stock" if req.first_supply else "ordered")
        if req.reason == ReplenishmentReason.TARGET_SHORTFALL:
            if req.first_supply:
                return f"Latest stock: a new {vocab.item} sent by the warehouse", "Latest stock"
            return f"Sent by the warehouse to top up {your} agreed level", "top-up"
        if req.reason == ReplenishmentReason.TRANSFER:
            gave = "you passed" if dealer_view else "passed"
            return f"Replacement for {vocab.items} {gave} to another {vocab.partner} ({req.origin_number})", "replacing transfers"
        return "Sent by the warehouse", "from the warehouse"

    def from_dealer(t: Transfer | None, number: str | None) -> str:
        name = None if dealer_view or t is None else other_dealers.get(t.source_reseller_id)
        source = name.business_name if name else f"another {vocab.partner}"
        return f"Moved in from {source}" + (f" ({number})" if number else "")

    arrivals: list[dict] = []

    def add(on, qty: int, reason: str, group: str, reference: str | None) -> None:
        """reference: the delivery number shown beside the date (other documents are named in the reason)."""
        arrivals.append({"on": on, "qty": qty, "reason": reason, "group": group, "reference": reference})

    for qty, t in rows:
        on, ref = t.occurred_at, t.reference_number
        if t.reference_type == "delivery" and t.reference_id in deliveries:
            d = deliveries[t.reference_id]
            on = d.delivered_on or on
            late = t.txn_type == TxnType.TRANSIT_RESOLUTION
            if t.txn_type == TxnType.TRANSIT_RESOLUTION and loc.type == LocationType.WAREHOUSE:
                add(on, qty, f"Came back from delivery {d.number}", "returned", None)
                continue
            left = qty
            pieces = [ln for ln in lines_by_delivery.get(d.id, []) if (ln.qty_late_received if late else ln.qty_received)]
            for i, ln in enumerate(pieces):
                part = left if i == len(pieces) - 1 else min(left, ln.qty_late_received if late else ln.qty_received)
                if part <= 0:
                    break
                left -= part
                req = requests.get(ln.request_id)
                reason, group = for_request(req) if req else ("Sent by the warehouse", "from the warehouse")
                add(on, part, reason, group, d.number)
            if left > 0:
                add(on, left, "Sent by the warehouse", "from the warehouse", d.number)
            continue
        match t.txn_type:
            case TxnType.OPENING_BALANCE if (t.reason or "").startswith("Initial stock"):
                by = who(t.actor_user_id)
                add(on, qty, f"Part of {your} initial stock" + (f", recorded by {by}" if by else ""), "initial stock",
                    None)
            case TxnType.OPENING_BALANCE:
                by = who(t.actor_user_id)
                add(on, qty, "Opening stock" + (f", recorded by {by}" if by else ""), "opening stock", None)
            case TxnType.INITIAL_STOCK_CORRECTION:
                by = who(t.actor_user_id)
                add(on, qty, f"Added to {your} initial stock by a correction" + (f", recorded by {by}" if by else ""),
                    "initial stock", None)
            case TxnType.SUPPLIER_RECEIPT:
                add(on, qty, "Received from the supplier" + (f" ({ref})" if ref else ""), "from the supplier", None)
            case TxnType.TRANSFER_RECEIPT:
                add(on, qty, from_dealer(transfers.get(t.reference_id), ref), f"from another {vocab.partner}", None)
            case TxnType.TRANSIT_RESOLUTION if t.reference_type == "transfer":
                if (t.reason or "").startswith("LATE_DELIVERY"):
                    add(on, qty, from_dealer(transfers.get(t.reference_id), ref), f"from another {vocab.partner}", None)
                else:
                    add(on, qty, f"Came back: transfer {ref} did not go ahead", "returned", None)
            case TxnType.STOCKTAKE_ADJUSTMENT:
                add(on, qty, f"Extra {vocab.item} found at stock check {ref or ''}".rstrip(), "found at stock check", None)
            case TxnType.SALE_REVERSAL:
                add(on, qty, f"Back in stock: sale {ref or ''} was cancelled".replace("  ", " "), "returned", None)
            case TxnType.ADJUSTMENT:
                by = who(t.actor_user_id)
                add(on, qty, "Stock correction" + (f" by {by}" if by else ""), "correction", None)
            case _:
                add(on, qty, t.txn_type.value.replace("_", " ").capitalize(), "other", None)

    # 3. What today's stock is made of: assume the oldest tyres are sold first, so the newest arrivals remain.
    remaining = on_hand
    in_stock: dict[str, int] = {}
    for a in arrivals:
        if remaining <= 0:
            break
        take = min(a["qty"], remaining)
        in_stock[a["group"]] = in_stock.get(a["group"], 0) + take
        remaining -= take
    if remaining > 0:
        in_stock["earlier stock"] = remaining

    return {
        "location_id": location_id, "product_id": product_id, "on_hand": on_hand,
        "arrivals": arrivals[:MAX_SHOWN], "more": len(arrivals) > MAX_SHOWN,
        "in_stock": [{"label": k, "qty": v} for k, v in in_stock.items()],
    }
