"""Read-only reports (BC §11). Never modifies data."""

from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.lookups import Names
from app.modules.audit.models import AuditEvent
from app.modules.catalogue.models import Product
from app.modules.customers.initial_stock_correction import ACTION as CORRECTION_ACTION
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from app.modules.inventory.models import Bucket, InventoryEntry, InventoryTransaction, StockBalance, TxnType
from app.modules.invoicing.models import Invoice, InvoiceLine
from app.modules.purchasing.service import incoming_by_product
from app.modules.replenishment.models import (
    OPEN_STATUSES,
    PRIORITY_RANK,
    Delivery,
    DeliveryStatus,
    ReplenishmentAllocation,
    ReplenishmentRequest,
)
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine, InvoiceStatus
from app.modules.stocktakes.models import Stocktake, StocktakeLine, StocktakeStatus
from app.modules.transfers.models import OPEN_TRANSFER_STATUSES, Transfer, TransferStatus

ZERO = Decimal("0")


def _open_requests(db: Session, reseller_id: int | None = None):
    stmt = select(ReplenishmentRequest).where(ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]))
    if reseller_id is not None:
        stmt = stmt.where(ReplenishmentRequest.reseller_id == reseller_id)
    return list(db.execute(stmt).scalars())


# ---------------------------------------------------------------------------
# 11.1 Total consignment stock
# ---------------------------------------------------------------------------


def consignment_stock(db: Session, *, reseller_id: int | None = None, location_id: int | None = None,
                      brand: str | None = None, sku: str | None = None, width: int | None = None,
                      aspect_ratio: int | None = None, rim_diameter: float | None = None,
                      availability: str | None = None, include_value: bool = False) -> dict:
    stmt = (
        select(StockBalance, Location, Reseller, Product)
        .join(Location, Location.id == StockBalance.location_id)
        .join(Reseller, Reseller.id == Location.reseller_id)
        .join(Product, Product.id == StockBalance.product_id)
        .where(Location.type == LocationType.CONSIGNMENT, StockBalance.on_hand > 0)
    )
    if reseller_id is not None:
        stmt = stmt.where(Location.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(Location.id == location_id)
    if brand:
        stmt = stmt.where(Product.brand.ilike(brand))
    if sku:
        stmt = stmt.where(Product.sku.ilike(f"%{sku}%"))
    if width:
        stmt = stmt.where(Product.width == width)
    if aspect_ratio:
        stmt = stmt.where(Product.aspect_ratio == aspect_ratio)
    if rim_diameter:
        stmt = stmt.where(Product.rim_diameter == rim_diameter)
    if availability == "available":
        stmt = stmt.where(StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked > 0)
    elif availability == "reserved":
        stmt = stmt.where(StockBalance.reserved > 0)
    elif availability == "blocked":
        stmt = stmt.where(StockBalance.blocked > 0)
    rows = []
    totals = {"on_hand": 0, "reserved": 0, "blocked": 0, "available": 0, "value": ZERO}
    for b, loc, r, p in db.execute(stmt.order_by(Reseller.business_name, Location.code, Product.sku)).tuples():
        value = (p.cost_price or ZERO) * b.on_hand if include_value else None
        rows.append({
            "reseller_id": r.id, "reseller_name": r.business_name, "account_ref": r.account_ref,
            "location_id": loc.id, "location_code": loc.code, "product_id": p.id, "sku": p.sku, "brand": p.brand,
            "size": p.size_display, "product_name": p.display_name, "on_hand": b.on_hand, "reserved": b.reserved,
            "blocked": b.blocked, "available": b.available, "value": value,
        })
        for k in ("on_hand", "reserved", "blocked", "available"):
            totals[k] += rows[-1][k]
        if include_value:
            totals["value"] += value
    transit = db.execute(
        select(func.coalesce(func.sum(StockBalance.on_hand), 0))
        .join(Location, Location.id == StockBalance.location_id).where(Location.type == LocationType.TRANSIT)
    ).scalar_one()
    return {"rows": rows, "totals": {**totals, "value": totals["value"] if include_value else None,
                                     "locations": len({r["location_id"] for r in rows}),
                                     "resellers": len({r["reseller_id"] for r in rows})},
            "in_transit_total": int(transit),
            "note": "Unsold dealership-owned stock at dealer locations. Sold stock is excluded; stock in transit "
                    "is reported separately and not included in location totals."}


# ---------------------------------------------------------------------------
# 11.2 Backorders awaiting replenishment
# ---------------------------------------------------------------------------


def backorders(db: Session, *, reseller_id: int | None = None, product_id: int | None = None,
               reason: str | None = None, priority: str | None = None, include_fully_allocated: bool = True) -> dict:
    reqs = _open_requests(db, reseller_id)
    if product_id is not None:
        reqs = [r for r in reqs if r.product_id == product_id]
    if reason:
        reqs = [r for r in reqs if r.reason == reason]
    if priority:
        reqs = [r for r in reqs if r.priority == priority]
    if not include_fully_allocated:
        reqs = [r for r in reqs if r.qty_awaiting_supply > 0]
    names = Names(db)
    for r in reqs:
        names.add("reseller", r.reseller_id).add("location", r.location_id).add("product", r.product_id)
    names.resolve()
    now = datetime.now(UTC)
    reqs.sort(key=lambda r: (PRIORITY_RANK[r.priority], r.created_at))
    rows = [{
        "request_id": r.id, "number": r.number, "reseller_id": r.reseller_id,
        "reseller_name": names.reseller_name(r.reseller_id), "location_id": r.location_id,
        "location_code": names.loc_code(r.location_id),
        "product_id": r.product_id, "sku": names.sku(r.product_id), "reason": r.reason,
        "origin_number": r.origin_number, "qty_required": r.qty_required, "qty_outstanding": r.qty_outstanding,
        "qty_allocated": r.qty_allocated, "qty_in_transit": r.qty_in_transit,
        "qty_transfer_covered": r.qty_transfer_covered, "qty_awaiting_supply": r.qty_awaiting_supply,
        "priority": r.priority, "expected_date": r.expected_date, "status": r.status,
        "age_days": (now - r.created_at).days,
    } for r in reqs]
    by_reason: dict[str, int] = defaultdict(int)
    by_reseller: dict[str, int] = defaultdict(int)
    by_sku: dict[str, int] = defaultdict(int)
    for row in rows:
        by_reason[row["reason"]] += row["qty_outstanding"]
        by_reseller[row["reseller_name"]] += row["qty_outstanding"]
        by_sku[row["sku"]] += row["qty_outstanding"]
    return {
        "rows": rows,
        "totals": {
            "requests": len(rows),
            "qty_outstanding": sum(r["qty_outstanding"] for r in rows),
            "qty_allocated": sum(r["qty_allocated"] for r in rows),
            "qty_in_transit": sum(r["qty_in_transit"] for r in rows),
            "qty_transfer_covered": sum(r["qty_transfer_covered"] for r in rows),
            "qty_awaiting_supply": sum(r["qty_awaiting_supply"] for r in rows),
        },
        "by_reason": dict(by_reason), "by_reseller": dict(by_reseller), "by_sku": dict(by_sku),
    }


# ---------------------------------------------------------------------------
# 11.3 Reseller transaction history
# ---------------------------------------------------------------------------

_CATEGORY = {
    TxnType.OPENING_BALANCE: "OPENING_BALANCE",
    TxnType.INITIAL_STOCK_CORRECTION: "INITIAL_STOCK_CORRECTION",
    TxnType.REPLENISHMENT_RECEIPT: "REPLENISHMENT",
    TxnType.TRANSFER_RECEIPT: "TRANSFER_IN",
    TxnType.TRANSFER_COLLECTION: "TRANSFER_OUT",
    TxnType.CONSIGNMENT_SALE: "SALE",
    TxnType.SALE_REVERSAL: "SALE_REVERSAL",
    TxnType.ADJUSTMENT: "ADJUSTMENT",
    TxnType.STOCKTAKE_ADJUSTMENT: "ADJUSTMENT",
    TxnType.WRITE_OFF: "WRITE_OFF",
    TxnType.SUPPLIER_RECEIPT: "RECEIPT",
}


def _category(txn: InventoryTransaction, qty: int) -> str:
    if txn.txn_type == TxnType.TRANSIT_RESOLUTION:
        if txn.reference_type == "transfer":
            return "TRANSFER_IN" if (txn.reason or "").startswith("LATE_DELIVERY") else "TRANSFER_RETURN"
        return "REPLENISHMENT"
    return _CATEGORY.get(txn.txn_type, txn.txn_type.value)


def reseller_history(db: Session, reseller_id: int, *, location_id: int | None = None, product_id: int | None = None,
                     date_from: date | None = None, date_to: date | None = None,
                     redact_counterparties: bool = False) -> dict:
    reseller = db.get(Reseller, reseller_id)
    locs = [loc for loc in db.execute(select(Location).where(Location.reseller_id == reseller_id)).scalars()
            if location_id is None or loc.id == location_id]
    loc_ids = [loc.id for loc in locs]
    start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
    end = datetime.combine(date_to, time.max, tzinfo=UTC) if date_to else None

    base = (select(InventoryEntry, InventoryTransaction)
            .join(InventoryTransaction, InventoryTransaction.id == InventoryEntry.transaction_id)
            .where(InventoryEntry.location_id.in_(loc_ids or [-1])))
    if product_id is not None:
        base = base.where(InventoryEntry.product_id == product_id)

    # Opening balances per (location, product) before the period.
    opening: dict[tuple[int, int], int] = defaultdict(int)
    if start is not None:
        for (e, _t) in db.execute(base.where(InventoryEntry.bucket == Bucket.ON_HAND,
                                             InventoryTransaction.occurred_at < start)).tuples():
            opening[(e.location_id, e.product_id)] += e.quantity

    period = base.where(InventoryEntry.bucket == Bucket.ON_HAND)
    if start is not None:
        period = period.where(InventoryTransaction.occurred_at >= start)
    if end is not None:
        period = period.where(InventoryTransaction.occurred_at <= end)
    entries = db.execute(period.order_by(InventoryTransaction.occurred_at, InventoryTransaction.id,
                                         InventoryEntry.id)).tuples().all()

    names = Names(db)
    for e, t in entries:
        names.add("product", e.product_id).add("location", e.location_id).add("user", t.actor_user_id)
    for (_, pid) in opening:
        names.add("product", pid)
    names.resolve()

    # Business-document enrichment.
    sale_ids = {t.reference_id for _, t in entries if t.reference_type == "consignment_sale"}
    transfer_ids = {t.reference_id for _, t in entries if t.reference_type == "transfer"}
    sale_invoices: dict[tuple[int, int], list[str]] = defaultdict(list)
    if sale_ids:
        for sale_id, prod_id, inv_no in db.execute(
            select(ConsignmentSaleLine.sale_id, ConsignmentSaleLine.product_id, Invoice.number)
            .join(InvoiceLine, and_(InvoiceLine.sale_line_id == ConsignmentSaleLine.id, InvoiceLine.is_active))
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .where(ConsignmentSaleLine.sale_id.in_(sale_ids))
        ).all():
            sale_invoices[(sale_id, prod_id)].append(inv_no)
    transfers = {t.id: t for t in db.execute(select(Transfer).where(Transfer.id.in_(transfer_ids or [-1]))).scalars()}
    t_names = Names(db)
    for tr in transfers.values():
        t_names.add("location", tr.source_location_id, tr.destination_location_id)
        t_names.add("reseller", tr.source_reseller_id, tr.destination_reseller_id).add("user", tr.approved_by_user_id)
    t_names.resolve()
    src_req_numbers = dict(db.execute(select(ReplenishmentRequest.id, ReplenishmentRequest.number).where(
        ReplenishmentRequest.id.in_([tr.source_request_id for tr in transfers.values() if tr.source_request_id]
                                    or [-1]))).all())

    running = dict(opening)
    rows = []
    for e, t in entries:
        key = (e.location_id, e.product_id)
        running[key] = running.get(key, 0) + e.quantity
        row = {
            "occurred_at": t.occurred_at, "transaction_number": t.number, "txn_type": t.txn_type,
            "category": _category(t, e.quantity), "location_code": names.loc_code(e.location_id),
            "product_id": e.product_id, "sku": names.sku(e.product_id),
            "qty_in": e.quantity if e.quantity > 0 else 0, "qty_out": -e.quantity if e.quantity < 0 else 0,
            "running_balance": running[key], "reference_type": t.reference_type, "reference_id": t.reference_id,
            "reference_number": t.reference_number, "reason": t.reason, "actor": names.user_name(t.actor_user_id),
            "invoice_numbers": [], "transfer": None,
        }
        if t.reference_type == "consignment_sale":
            row["invoice_numbers"] = sale_invoices.get((t.reference_id, e.product_id), [])
        if t.reference_type == "transfer" and t.reference_id in transfers:
            tr = transfers[t.reference_id]
            def party(rid, lid):
                if redact_counterparties and rid != reseller_id:
                    return "Another dealer"
                return f"{t_names.reseller_name(rid)} ({t_names.loc_code(lid)})"

            row["transfer"] = {
                "id": tr.id, "number": tr.number, "status": tr.status,
                "source": party(tr.source_reseller_id, tr.source_location_id),
                "destination": party(tr.destination_reseller_id, tr.destination_location_id),
                "reason": tr.reason, "approved_by": t_names.user_name(tr.approved_by_user_id),
                "approval_notes": tr.approval_notes, "source_consent_reference": tr.source_consent_reference,
                "linked_backorder": src_req_numbers.get(tr.source_request_id),
            }
        rows.append(row)

    # Outstanding obligations, keeping sales-driven and transfer-driven demand separate (BC §8).
    open_reqs = [r for r in _open_requests(db, reseller_id) if location_id is None or r.location_id == location_id]
    if product_id is not None:
        open_reqs = [r for r in open_reqs if r.product_id == product_id]
    o_names = Names(db).add("product", *[r.product_id for r in open_reqs]).add(
        "location", *[r.location_id for r in open_reqs]).resolve()
    obligations = [{
        "request_id": r.id, "number": r.number, "reason": r.reason, "origin_number": r.origin_number,
        "location_code": o_names.loc_code(r.location_id), "sku": o_names.sku(r.product_id),
        "qty_outstanding": r.qty_outstanding, "qty_awaiting_supply": r.qty_awaiting_supply, "status": r.status,
    } for r in open_reqs]
    by_reason: dict[str, int] = defaultdict(int)
    for o in obligations:
        by_reason[o["reason"]] += o["qty_outstanding"]

    closing = {f"{names.loc_code(k[0])}|{names.sku(k[1])}": v for k, v in running.items()}
    return {
        "reseller": {"id": reseller.id, "name": reseller.business_name, "account_ref": reseller.account_ref},
        "period": {"from": date_from, "to": date_to},
        "opening_balances": [{"location_code": names.loc_code(k[0]), "sku": names.sku(k[1]), "quantity": v}
                             for k, v in sorted(opening.items()) if v],
        "rows": rows,
        "closing_balances": [{"key": k, "quantity": v} for k, v in sorted(closing.items())],
        "outstanding_obligations": obligations,
        "outstanding_by_reason": dict(by_reason),
        "outstanding_total": sum(o["qty_outstanding"] for o in obligations),
    }


# ---------------------------------------------------------------------------
# Additional views
# ---------------------------------------------------------------------------


def warehouse_availability(db: Session) -> list[dict]:
    incoming = incoming_by_product(db)
    demand: dict[int, int] = defaultdict(int)
    for r in _open_requests(db):
        demand[r.product_id] += r.qty_awaiting_supply
    rows = db.execute(
        select(StockBalance, Location, Product)
        .join(Location, Location.id == StockBalance.location_id).join(Product, Product.id == StockBalance.product_id)
        .where(Location.type == LocationType.WAREHOUSE)
    ).tuples().all()
    seen = set()
    out = []
    for b, loc, p in rows:
        seen.add(p.id)
        out.append({"location_code": loc.code, "product_id": p.id, "sku": p.sku, "product_name": p.display_name,
                    "on_hand": b.on_hand, "reserved": b.reserved, "blocked": b.blocked, "available": b.available,
                    "incoming": incoming.get(p.id, 0), "awaiting_supply_demand": demand.get(p.id, 0)})
    # Products with demand or incoming supply but no warehouse balance row.
    missing = (set(incoming) | {k for k, v in demand.items() if v}) - seen
    names = Names(db).add("product", *missing).resolve()
    for pid in missing:
        out.append({"location_code": None, "product_id": pid, "sku": names.sku(pid),
                    "product_name": names.product_name(pid), "on_hand": 0, "reserved": 0, "blocked": 0,
                    "available": 0, "incoming": incoming.get(pid, 0), "awaiting_supply_demand": demand.get(pid, 0)})
    return sorted(out, key=lambda r: (r["sku"] or "", r["location_code"] or ""))


def demand_by_sku(db: Session) -> list[dict]:
    incoming = incoming_by_product(db)
    agg: dict[int, dict] = {}
    for r in _open_requests(db):
        a = agg.setdefault(r.product_id, {"outstanding": 0, "allocated": 0, "in_transit": 0, "transfer_covered": 0,
                                          "awaiting_supply": 0, "requests": 0, "sale": 0, "transfer": 0, "other": 0})
        a["outstanding"] += r.qty_outstanding
        a["allocated"] += r.qty_allocated
        a["in_transit"] += r.qty_in_transit
        a["transfer_covered"] += r.qty_transfer_covered
        a["awaiting_supply"] += r.qty_awaiting_supply
        a["requests"] += 1
        a[{"SALE": "sale", "TRANSFER": "transfer"}.get(r.reason, "other")] += r.qty_outstanding
    wh_avail = dict(db.execute(
        select(StockBalance.product_id, func.sum(StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked))
        .join(Location, Location.id == StockBalance.location_id).where(Location.type == LocationType.WAREHOUSE)
        .group_by(StockBalance.product_id)).all())
    names = Names(db).add("product", *agg.keys()).resolve()
    return sorted([{"product_id": pid, "sku": names.sku(pid), "product_name": names.product_name(pid), **a,
                    "warehouse_available": int(wh_avail.get(pid, 0) or 0), "incoming": incoming.get(pid, 0),
                    "uncovered_after_incoming": max(0, a["awaiting_supply"] - int(wh_avail.get(pid, 0) or 0)
                                                    - incoming.get(pid, 0))}
                   for pid, a in agg.items()], key=lambda r: -r["awaiting_supply"])


def uninvoiced_summary(db: Session) -> list[dict]:
    rows = db.execute(
        select(ConsignmentSale.reseller_id, ConsignmentSaleLine.invoice_status,
               func.sum(ConsignmentSaleLine.quantity - ConsignmentSaleLine.reversed_qty),
               func.sum((ConsignmentSaleLine.quantity - ConsignmentSaleLine.reversed_qty) * ConsignmentSaleLine.unit_price),
               func.min(ConsignmentSale.sale_date))
        .join(ConsignmentSale, ConsignmentSale.id == ConsignmentSaleLine.sale_id)
        .where(ConsignmentSaleLine.invoice_status.in_([InvoiceStatus.UNINVOICED.value, InvoiceStatus.DRAFTED.value]),
               ConsignmentSaleLine.quantity > ConsignmentSaleLine.reversed_qty)
        .group_by(ConsignmentSale.reseller_id, ConsignmentSaleLine.invoice_status)
    ).all()
    names = Names(db).add("reseller", *[r[0] for r in rows]).resolve()
    agg: dict[int, dict] = {}
    for rid, status, qty, value, oldest in rows:
        a = agg.setdefault(rid, {"reseller_id": rid, "reseller_name": names.reseller_name(rid), "uninvoiced_qty": 0,
                                 "uninvoiced_value": ZERO, "on_draft_qty": 0, "on_draft_value": ZERO,
                                 "oldest_sale_date": oldest})
        prefix = "uninvoiced" if status == InvoiceStatus.UNINVOICED else "on_draft"
        a[f"{prefix}_qty"] += int(qty)
        a[f"{prefix}_value"] += Decimal(value).quantize(Decimal("0.01"))
        a["oldest_sale_date"] = min(a["oldest_sale_date"], oldest)
    return sorted(agg.values(), key=lambda a: a["oldest_sale_date"])


def stocktake_discrepancies(db: Session, reseller_id: int | None = None) -> list[dict]:
    stmt = (select(StocktakeLine, Stocktake).join(Stocktake, Stocktake.id == StocktakeLine.stocktake_id)
            .where(Stocktake.status.in_([StocktakeStatus.SUBMITTED.value, StocktakeStatus.APPROVED.value]),
                   StocktakeLine.expected_qty.is_not(None), StocktakeLine.counted_qty != StocktakeLine.expected_qty))
    if reseller_id is not None:
        stmt = stmt.where(Stocktake.reseller_id == reseller_id)
    rows = db.execute(stmt.order_by(Stocktake.count_date.desc())).tuples().all()
    names = Names(db)
    for ln, st in rows:
        names.add("product", ln.product_id).add("location", st.location_id).add("reseller", st.reseller_id)
    names.resolve()
    return [{"stocktake_id": st.id, "number": st.number, "status": st.status, "count_date": st.count_date,
             "reseller_name": names.reseller_name(st.reseller_id), "location_code": names.loc_code(st.location_id),
             "sku": names.sku(ln.product_id), "expected_qty": ln.expected_qty, "counted_qty": ln.counted_qty,
             "variance": ln.variance, "qty_sold": ln.qty_sold, "qty_missing": ln.qty_missing,
             "counted_damaged_qty": ln.counted_damaged_qty} for ln, st in rows]


def consignment_ageing(db: Session) -> list[dict]:
    """Days since each consignment location last received or sold each SKU (slow-moving indicator)."""
    last_move = db.execute(
        select(InventoryEntry.location_id, InventoryEntry.product_id, func.max(InventoryTransaction.occurred_at))
        .join(InventoryTransaction, InventoryTransaction.id == InventoryEntry.transaction_id)
        .join(Location, Location.id == InventoryEntry.location_id)
        .where(Location.type == LocationType.CONSIGNMENT, InventoryEntry.bucket == Bucket.ON_HAND)
        .group_by(InventoryEntry.location_id, InventoryEntry.product_id)
    ).all()
    last_sale = dict(((loc, pid), ts) for loc, pid, ts in db.execute(
        select(InventoryEntry.location_id, InventoryEntry.product_id, func.max(InventoryTransaction.occurred_at))
        .join(InventoryTransaction, InventoryTransaction.id == InventoryEntry.transaction_id)
        .where(InventoryTransaction.txn_type == TxnType.CONSIGNMENT_SALE, InventoryEntry.bucket == Bucket.ON_HAND,
               InventoryEntry.quantity < 0)
        .group_by(InventoryEntry.location_id, InventoryEntry.product_id)).all())
    balances = {(b.location_id, b.product_id): b for b in db.execute(
        select(StockBalance).join(Location, Location.id == StockBalance.location_id)
        .where(Location.type == LocationType.CONSIGNMENT, StockBalance.on_hand > 0)).scalars()}
    names = Names(db)
    for loc, pid in balances:
        names.add("location", loc).add("product", pid)
    names.resolve()
    now = datetime.now(UTC)
    lm = {(loc, pid): ts for loc, pid, ts in last_move}
    out = []
    for key, b in balances.items():
        ls = last_sale.get(key)
        out.append({"location_code": names.loc_code(key[0]), "sku": names.sku(key[1]), "on_hand": b.on_hand,
                    "last_movement": lm.get(key), "last_sale": ls,
                    "days_since_sale": (now - ls).days if ls else None,
                    "days_since_movement": (now - lm[key]).days if key in lm else None})
    return sorted(out, key=lambda r: -(r["days_since_sale"] if r["days_since_sale"] is not None else 10**6))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def dashboard(db: Session, reseller_id: int | None = None) -> dict:
    def total(loc_type: LocationType, column):
        stmt = (select(func.coalesce(func.sum(column), 0)).select_from(StockBalance)
                .join(Location, Location.id == StockBalance.location_id).where(Location.type == loc_type))
        if reseller_id is not None:
            stmt = stmt.where(Location.reseller_id == reseller_id)
        return int(db.execute(stmt).scalar_one())

    reqs = _open_requests(db, reseller_id)
    now = datetime.now(UTC)
    transfers_stmt = select(Transfer).where(Transfer.status.in_([s.value for s in OPEN_TRANSFER_STATUSES]))
    deliveries_stmt = select(func.count()).select_from(Delivery).where(
        Delivery.status.in_([DeliveryStatus.IN_TRANSIT.value, DeliveryStatus.RECEIVED_WITH_DISCREPANCY.value]))
    uninv_stmt = (select(func.coalesce(func.sum(ConsignmentSaleLine.quantity - ConsignmentSaleLine.reversed_qty), 0),
                         func.coalesce(func.sum((ConsignmentSaleLine.quantity - ConsignmentSaleLine.reversed_qty)
                                                * ConsignmentSaleLine.unit_price), 0))
                  .join(ConsignmentSale, ConsignmentSale.id == ConsignmentSaleLine.sale_id)
                  .where(ConsignmentSaleLine.invoice_status.in_([InvoiceStatus.UNINVOICED.value,
                                                                 InvoiceStatus.DRAFTED.value])))
    if reseller_id is not None:
        transfers_stmt = transfers_stmt.where(or_(Transfer.source_reseller_id == reseller_id,
                                                  Transfer.destination_reseller_id == reseller_id))
        deliveries_stmt = deliveries_stmt.where(Delivery.reseller_id == reseller_id)
        uninv_stmt = uninv_stmt.where(ConsignmentSale.reseller_id == reseller_id)
    open_transfers = list(db.execute(transfers_stmt).scalars())
    uninv_qty, uninv_value = db.execute(uninv_stmt).one()
    awaiting_dispatch = db.execute(
        select(func.coalesce(func.sum(ReplenishmentAllocation.quantity - ReplenishmentAllocation.dispatched_qty
                                      - ReplenishmentAllocation.released_qty), 0))
        .join(ReplenishmentRequest, ReplenishmentRequest.id == ReplenishmentAllocation.request_id)
        .where(ReplenishmentAllocation.status == "ACTIVE",
               *( [ReplenishmentRequest.reseller_id == reseller_id] if reseller_id is not None else []))
    ).scalar_one()
    attention = [r for r in reqs if r.qty_awaiting_supply > 0 and
                 (r.priority in ("URGENT", "HIGH") or (now - r.created_at).days >= 7
                  or (r.expected_date is not None and r.expected_date < date.today()))]
    return {
        "warehouse": None if reseller_id is not None else {
            "on_hand": total(LocationType.WAREHOUSE, StockBalance.on_hand),
            "reserved": total(LocationType.WAREHOUSE, StockBalance.reserved),
            "blocked": total(LocationType.WAREHOUSE, StockBalance.blocked),
            "available": total(LocationType.WAREHOUSE,
                               StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked),
        },
        "consignment": {
            "on_hand": total(LocationType.CONSIGNMENT, StockBalance.on_hand),
            "available": total(LocationType.CONSIGNMENT,
                               StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked),
        },
        "in_transit": None if reseller_id is not None else total(LocationType.TRANSIT, StockBalance.on_hand),
        "backorders": {
            "requests": sum(1 for r in reqs if r.qty_awaiting_supply > 0),
            "qty_awaiting_supply": sum(r.qty_awaiting_supply for r in reqs),
            "qty_outstanding": sum(r.qty_outstanding for r in reqs),
        },
        "awaiting_dispatch_qty": int(awaiting_dispatch),
        "open_deliveries": int(db.execute(deliveries_stmt).scalar_one()),
        "transfers_in_progress": {
            "count": len(open_transfers),
            "awaiting_approval": sum(1 for t in open_transfers if t.status == TransferStatus.REQUESTED),
            "in_transit": sum(1 for t in open_transfers if t.status == TransferStatus.IN_TRANSIT),
            "discrepancies": sum(1 for t in open_transfers if t.status == TransferStatus.RECEIVED_WITH_DISCREPANCY),
        },
        "sales_awaiting_invoicing": {"qty": int(uninv_qty), "value": Decimal(uninv_value).quantize(Decimal("0.01"))},
        "replenishment_attention": {
            "count": len(attention),
            "items": [{"request_id": r.id, "number": r.number, "reseller_id": r.reseller_id,
                       "priority": r.priority, "qty_awaiting_supply": r.qty_awaiting_supply,
                       "age_days": (now - r.created_at).days, "expected_date": r.expected_date}
                      for r in sorted(attention, key=lambda r: (PRIORITY_RANK[r.priority], r.created_at))[:10]],
        },
    }


# ---------------------------------------------------------------------------
# Initial stock corrections (from the change history, which keeps before → after and the reason)
# ---------------------------------------------------------------------------

def stock_corrections(db: Session, reseller_id: int | None = None, date_from: date | None = None,
                      date_to: date | None = None) -> dict:
    q = (select(AuditEvent, User.full_name, Reseller.business_name, InventoryTransaction.number)
         .outerjoin(User, User.id == AuditEvent.actor_user_id)
         .outerjoin(Reseller, Reseller.id == AuditEvent.reseller_id)
         .outerjoin(InventoryTransaction, InventoryTransaction.id == AuditEvent.entity_id)
         .where(AuditEvent.action == CORRECTION_ACTION))
    if reseller_id is not None:
        q = q.where(AuditEvent.reseller_id == reseller_id)
    if date_from is not None:
        q = q.where(func.date(AuditEvent.occurred_at) >= date_from)
    if date_to is not None:
        q = q.where(func.date(AuditEvent.occurred_at) <= date_to)
    rows = []
    for ev, by, dealer, number in db.execute(q.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())).all():
        d = ev.details or {}
        for c in d.get("changes", []):
            rows.append({
                "corrected_at": ev.occurred_at, "transaction_number": number, "corrects": d.get("corrects_transaction"),
                "reseller_id": ev.reseller_id, "reseller_name": dealer, "location_code": d.get("location"),
                "sku": c["sku"], "before": c["before"], "after": c["after"], "change": c["after"] - c["before"],
                "corrected_by": by, "reason": d.get("reason"),
            })
    return {"rows": rows, "corrections": len({r["transaction_number"] for r in rows})}
