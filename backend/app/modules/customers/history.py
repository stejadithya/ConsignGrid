"""Dealer history at a glance (staff): when the dealer joined, with what stock, first consignment and sales so far.

Read-only, built from the dealer record, the audit log, the stock ledger and sales; nothing new is stored.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.industry import vocab
from app.modules.audit.models import AuditEvent
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, Reseller
from app.modules.identity.models import User
from app.modules.inventory.models import Bucket, InventoryEntry, InventoryTransaction, TxnType
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine


@dataclass
class StockLine:
    product_id: int
    sku: str
    name: str
    quantity: int                 # after any initial stock corrections
    recorded: int | None = None   # as first entered, when a correction changed it


@dataclass
class Arrival:
    occurred_at: datetime
    transaction_number: str
    txn_type: str
    reference_number: str | None


@dataclass
class LastSale:
    id: int
    number: str
    sale_date: date
    units: int


@dataclass
class DealerHistory:
    reseller_id: int
    onboarded_at: datetime
    onboarded_by: str | None
    dealer_type: str                       # EXISTING: joined with stock (initial or opening stock); NEW otherwise
    first_stock: Arrival | None
    onboarding_stock_kind: str | None      # INITIAL_STOCK or FIRST_DELIVERY
    onboarding_stock_at: datetime | None
    onboarding_stock: list[StockLine] = field(default_factory=list)
    units_sold: int = 0
    sales_count: int = 0
    last_sale: LastSale | None = None
    corrections: int = 0                   # initial stock corrections made (see initial_stock_correction)


def dealer_history(db: Session, reseller_id: int) -> DealerHistory:
    reseller = db.get(Reseller, reseller_id)
    if reseller is None:
        raise NotFoundError(f"{vocab.Partner} not found")
    loc_ids = list(db.execute(select(Location.id).where(Location.reseller_id == reseller_id)).scalars())

    creator = db.execute(select(User.full_name).join(AuditEvent, AuditEvent.actor_user_id == User.id)
                         .where(AuditEvent.action == "reseller.create", AuditEvent.entity_id == reseller_id)
                         .order_by(AuditEvent.id).limit(1)).scalar_one_or_none()

    # Stock arriving at the dealer's shops, oldest first (positive on-hand entries).
    arrivals = db.execute(
        select(InventoryTransaction, InventoryEntry.product_id, InventoryEntry.quantity)
        .join(InventoryEntry, InventoryEntry.transaction_id == InventoryTransaction.id)
        .where(InventoryEntry.location_id.in_(loc_ids), InventoryEntry.bucket == Bucket.ON_HAND, InventoryEntry.quantity > 0)
        .order_by(InventoryTransaction.occurred_at, InventoryTransaction.id)
    ).all() if loc_ids else []
    first = arrivals[0][0] if arrivals else None
    opening = [(t, pid, q) for t, pid, q in arrivals if t.txn_type == TxnType.OPENING_BALANCE]
    if opening:
        kind, chosen = "INITIAL_STOCK", opening
    elif first is not None:
        kind, chosen = "FIRST_DELIVERY", [(t, pid, q) for t, pid, q in arrivals if t.id == first.id]
    else:
        kind, chosen = None, []
    qty_by_product: dict[int, int] = {}
    for _, pid, q in chosen:
        qty_by_product[pid] = qty_by_product.get(pid, 0) + q
    # Initial stock corrections (both ways) change what the dealer joined with; the first figures are kept alongside.
    recorded = dict(qty_by_product)
    fixes = db.execute(
        select(InventoryEntry.transaction_id, InventoryEntry.product_id, InventoryEntry.quantity)
        .join(InventoryTransaction, InventoryTransaction.id == InventoryEntry.transaction_id)
        .where(InventoryTransaction.txn_type == TxnType.INITIAL_STOCK_CORRECTION,
               InventoryTransaction.reverses_transaction_id.in_({t.id for t, _, _ in opening}),
               InventoryEntry.location_id.in_(loc_ids), InventoryEntry.bucket == Bucket.ON_HAND)
    ).all() if opening else []
    for _, pid, q in fixes:
        qty_by_product[pid] = qty_by_product.get(pid, 0) + q
    products = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(list(qty_by_product)))).scalars()}
    lines = sorted((StockLine(product_id=pid, sku=products[pid].sku, name=products[pid].display_name, quantity=q,
                              recorded=recorded.get(pid, 0) if q != recorded.get(pid, 0) else None)
                    for pid, q in qty_by_product.items() if q or recorded.get(pid)), key=lambda ln: ln.sku)

    net = ConsignmentSaleLine.quantity - ConsignmentSaleLine.reversed_qty
    units, count = db.execute(
        select(func.coalesce(func.sum(net), 0), func.count(func.distinct(ConsignmentSale.id)))
        .join(ConsignmentSale, ConsignmentSale.id == ConsignmentSaleLine.sale_id)
        .where(ConsignmentSale.reseller_id == reseller_id)
    ).one()
    last = db.execute(
        select(ConsignmentSale, func.sum(net).label("units"))
        .join(ConsignmentSaleLine, ConsignmentSaleLine.sale_id == ConsignmentSale.id)
        .where(ConsignmentSale.reseller_id == reseller_id)
        .group_by(ConsignmentSale.id)
        .order_by(ConsignmentSale.sale_date.desc(), ConsignmentSale.id.desc()).limit(1)
    ).first()

    return DealerHistory(
        reseller_id=reseller.id, onboarded_at=reseller.created_at, onboarded_by=creator,
        dealer_type="EXISTING" if opening else "NEW",
        first_stock=Arrival(occurred_at=first.occurred_at, transaction_number=first.number, txn_type=first.txn_type,
                            reference_number=first.reference_number) if first else None,
        onboarding_stock_kind=kind, onboarding_stock_at=chosen[0][0].occurred_at if chosen else None,
        onboarding_stock=lines, units_sold=int(units), sales_count=int(count),
        last_sale=LastSale(id=last[0].id, number=last[0].number, sale_date=last[0].sale_date, units=int(last[1]))
        if last else None,
        corrections=len({tid for tid, _, _ in fixes}),
    )
