"""Purchase orders and goods receipts. Incoming quantities are never stock; receipts never auto-allocate (A-002)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.numbering import next_number
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType
from app.modules.identity.models import User
from app.modules.inventory.models import TxnType
from app.modules.inventory.service import Ledger, Ref, system_location
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    POStatus,
    PurchaseOrder,
    PurchaseOrderLine,
)


def _warehouse(db: Session, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.type != LocationType.WAREHOUSE or not loc.is_active:
        raise BusinessRuleError("Receiving location must be an active warehouse")
    return loc


def get_po(db: Session, po_id: int, lock: bool = False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id).options(selectinload(PurchaseOrder.lines))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    po = db.execute(stmt).scalar_one_or_none()
    if po is None:
        raise NotFoundError("Purchase order not found")
    return po


def create_po(db: Session, actor: User, *, supplier_name: str, supplier_reference: str | None,
              warehouse_location_id: int, expected_date: date | None, notes: str | None,
              lines: list[tuple[int, int, Decimal | None]]) -> PurchaseOrder:
    wh = _warehouse(db, warehouse_location_id)
    if not lines:
        raise BusinessRuleError("A purchase order needs at least one line")
    seen = set()
    po = PurchaseOrder(number=next_number(db, "PO"), supplier_name=supplier_name,
                       supplier_reference=supplier_reference, warehouse_location_id=wh.id,
                       expected_date=expected_date, notes=notes, created_by_user_id=actor.id, status=POStatus.OPEN)
    for product_id, qty, cost in lines:
        if product_id in seen:
            raise BusinessRuleError("Each product may appear only once per purchase order")
        seen.add(product_id)
        if db.get(Product, product_id) is None:
            raise NotFoundError(f"Product {product_id} not found")
        po.lines.append(PurchaseOrderLine(product_id=product_id, qty_ordered=qty, unit_cost=cost))
    db.add(po)
    db.flush()
    record_audit(db, actor_id=actor.id, action="po.create", entity_type="purchase_order", entity_id=po.id,
                 summary=f"Created {po.number} from {supplier_name}: {sum(ln.qty_ordered for ln in po.lines)} units")
    return po


def cancel_po(db: Session, actor: User, po_id: int, reason: str) -> PurchaseOrder:
    po = get_po(db, po_id, lock=True)
    if po.status not in (POStatus.OPEN,) or any(ln.qty_received > 0 for ln in po.lines):
        raise ConflictError("Only an open purchase order with no receipts can be cancelled")
    po.status = POStatus.CANCELLED
    record_audit(db, actor_id=actor.id, action="po.cancel", entity_type="purchase_order", entity_id=po.id,
                 summary=f"Cancelled {po.number}: {reason}")
    return po


def receive_goods(db: Session, actor: User, *, warehouse_location_id: int, purchase_order_id: int | None,
                  supplier_reference: str | None, notes: str | None,
                  lines: list[dict]) -> GoodsReceipt:
    """lines: {product_id, qty_received, qty_damaged, purchase_order_line_id?}."""
    wh = _warehouse(db, warehouse_location_id)
    po = None
    if purchase_order_id is not None:
        po = get_po(db, purchase_order_id, lock=True)
        if po.status in (POStatus.RECEIVED, POStatus.CANCELLED):
            raise ConflictError(f"{po.number} is {po.status}")
        if po.warehouse_location_id != wh.id:
            raise BusinessRuleError(f"{po.number} is for a different warehouse")
    if not lines:
        raise BusinessRuleError("Nothing to receive")

    receipt = GoodsReceipt(number=next_number(db, "GRN"), purchase_order_id=po.id if po else None,
                           warehouse_location_id=wh.id, supplier_reference=supplier_reference, notes=notes,
                           received_by_user_id=actor.id)
    db.add(receipt)
    db.flush()
    ref = Ref("goods_receipt", receipt.id, receipt.number)
    ledger = Ledger(db, TxnType.SUPPLIER_RECEIPT, actor_id=actor.id, ref=ref, notes=notes)
    receipt.inventory_transaction_id = ledger.txn.id
    supplier = system_location(db, LocationType.SUPPLIER)
    po_lines = {ln.id: ln for ln in po.lines} if po else {}
    for line in lines:
        qty, damaged = int(line["qty_received"]), int(line.get("qty_damaged") or 0)
        if qty <= 0 or damaged < 0 or damaged > qty:
            raise BusinessRuleError("Received quantity must be positive and damaged ≤ received")
        product_id = line.get("product_id")
        pol = None
        if po is not None:
            pol_id = line.get("purchase_order_line_id")
            pol = po_lines.get(pol_id) if pol_id else next(
                (pl for pl in po.lines if pl.product_id == product_id), None)
            if pol is None:
                raise BusinessRuleError(f"Product {product_id} is not on {po.number}")
            product_id = pol.product_id
            if pol.qty_received + qty > pol.qty_ordered:
                raise BusinessRuleError(
                    f"Over-receipt on {po.number}: ordered {pol.qty_ordered}, already received {pol.qty_received}"
                )
            pol.qty_received += qty
        if product_id is None or db.get(Product, product_id) is None:
            raise NotFoundError("Product not found")
        ledger.move(product_id, supplier, wh, qty)
        if damaged:
            ledger.block(wh, product_id, damaged)
        db.add(GoodsReceiptLine(goods_receipt_id=receipt.id, purchase_order_line_id=pol.id if pol else None,
                                product_id=product_id, qty_received=qty, qty_damaged=damaged))
    if po is not None:
        db.flush()
        if all(pl.qty_received >= pl.qty_ordered for pl in po.lines):
            po.status = POStatus.RECEIVED
        elif any(pl.qty_received > 0 for pl in po.lines):
            po.status = POStatus.PARTIALLY_RECEIVED
    db.flush()
    total = sum(int(ln["qty_received"]) for ln in lines)
    record_audit(db, actor_id=actor.id, action="goods.receive", entity_type="goods_receipt", entity_id=receipt.id,
                 summary=f"Received {receipt.number} at {wh.code}: {total} units" + (f" against {po.number}" if po else ""))
    db.refresh(receipt)
    return receipt


def list_pos(db: Session, *, status: POStatus | None = None, open_only: bool = False) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines))
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    if open_only:
        stmt = stmt.where(PurchaseOrder.status.in_([POStatus.OPEN.value, POStatus.PARTIALLY_RECEIVED.value]))
    return list(db.execute(stmt.order_by(PurchaseOrder.id.desc())).scalars())


def incoming_by_product(db: Session) -> dict[int, int]:
    """Ordered-but-not-received quantity per product on open POs. Not stock."""
    rows = db.execute(
        select(PurchaseOrderLine.product_id, func.sum(PurchaseOrderLine.qty_ordered - PurchaseOrderLine.qty_received))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(PurchaseOrder.status.in_([POStatus.OPEN.value, POStatus.PARTIALLY_RECEIVED.value]))
        .group_by(PurchaseOrderLine.product_id)
    ).all()
    return {pid: int(q) for pid, q in rows if q}


def list_receipts(db: Session, limit: int = 100) -> list[GoodsReceipt]:
    return list(db.execute(
        select(GoodsReceipt).options(selectinload(GoodsReceipt.lines)).order_by(GoodsReceipt.id.desc()).limit(limit)
    ).scalars())
