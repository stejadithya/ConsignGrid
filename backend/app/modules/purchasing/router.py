from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.lookups import Names
from app.core.permissions import P
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.purchasing import service
from app.modules.purchasing.models import GoodsReceipt, POStatus, PurchaseOrder
from app.modules.purchasing.schemas import (
    IncomingRow,
    POCreate,
    POLineOut,
    POOut,
    ReceiptCreate,
    ReceiptLineOut,
    ReceiptOut,
)
from app.modules.replenishment.models import OPEN_STATUSES, ReplenishmentRequest

router = APIRouter(prefix="/purchasing", tags=["purchasing"])
Reader = Annotated[User, Depends(require(P.INVENTORY_READ))]


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _staff(user: User):
    from app.core.errors import PermissionDeniedError

    if user.is_reseller_user:
        raise PermissionDeniedError("Not available to dealer users")


def po_out(db, pos: list[PurchaseOrder]) -> list[POOut]:
    names = Names(db)
    for po in pos:
        names.add("location", po.warehouse_location_id)
        names.add("product", *[ln.product_id for ln in po.lines])
    names.resolve()
    return [
        POOut(
            id=po.id, number=po.number, supplier_name=po.supplier_name, supplier_reference=po.supplier_reference,
            warehouse_location_id=po.warehouse_location_id, warehouse_code=names.loc_code(po.warehouse_location_id),
            expected_date=po.expected_date, status=po.status, notes=po.notes, created_at=po.created_at,
            lines=[POLineOut(id=ln.id, product_id=ln.product_id, sku=names.sku(ln.product_id),
                             product_name=names.product_name(ln.product_id), qty_ordered=ln.qty_ordered,
                             qty_received=ln.qty_received, qty_outstanding=ln.qty_outstanding, unit_cost=ln.unit_cost)
                   for ln in po.lines],
        )
        for po in pos
    ]


def receipt_out(db, receipts: list[GoodsReceipt]) -> list[ReceiptOut]:
    names = Names(db)
    for r in receipts:
        names.add("user", r.received_by_user_id).add("product", *[ln.product_id for ln in r.lines])
    names.resolve()
    out = []
    for r in receipts:
        pids = [ln.product_id for ln in r.lines]
        backorders = db.execute(
            select(func.count()).select_from(ReplenishmentRequest).where(
                ReplenishmentRequest.product_id.in_(pids),
                ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]),
                ReplenishmentRequest.qty_required - ReplenishmentRequest.qty_delivered
                - ReplenishmentRequest.qty_cancelled - ReplenishmentRequest.qty_allocated
                - ReplenishmentRequest.qty_in_transit - ReplenishmentRequest.qty_transfer_covered > 0,
            )
        ).scalar_one() if pids else 0
        out.append(ReceiptOut(
            id=r.id, number=r.number, purchase_order_id=r.purchase_order_id,
            warehouse_location_id=r.warehouse_location_id, supplier_reference=r.supplier_reference,
            received_at=r.received_at, received_by=names.user_name(r.received_by_user_id),
            inventory_transaction_id=r.inventory_transaction_id, notes=r.notes,
            lines=[ReceiptLineOut(id=ln.id, product_id=ln.product_id, sku=names.sku(ln.product_id),
                                  purchase_order_line_id=ln.purchase_order_line_id, qty_received=ln.qty_received,
                                  qty_damaged=ln.qty_damaged) for ln in r.lines],
            open_backorders_for_received_skus=backorders,
        ))
    return out


@router.get("/purchase-orders", response_model=list[POOut])
def list_pos(db: DB, user: Reader, status: POStatus | None = None, open_only: bool = False):
    _staff(user)
    return po_out(db, service.list_pos(db, status=status, open_only=open_only))


@router.get("/purchase-orders/{po_id}", response_model=POOut)
def get_po(po_id: int, db: DB, user: Reader):
    _staff(user)
    return po_out(db, [service.get_po(db, po_id)])[0]


@router.post("/purchase-orders", response_model=POOut, status_code=201)
def create_po(data: POCreate, db: DB, user: Annotated[User, Depends(require(P.PURCHASING_MANAGE))]):
    po = service.create_po(db, user, supplier_name=data.supplier_name, supplier_reference=data.supplier_reference,
                           warehouse_location_id=data.warehouse_location_id, expected_date=data.expected_date,
                           notes=data.notes, lines=[(ln.product_id, ln.qty_ordered, ln.unit_cost) for ln in data.lines])
    db.commit()
    return po_out(db, [service.get_po(db, po.id)])[0]


@router.post("/purchase-orders/{po_id}/cancel", response_model=POOut)
def cancel_po(po_id: int, data: Reason, db: DB, user: Annotated[User, Depends(require(P.PURCHASING_MANAGE))]):
    service.cancel_po(db, user, po_id, data.reason)
    db.commit()
    return po_out(db, [service.get_po(db, po_id)])[0]


@router.get("/receipts", response_model=list[ReceiptOut])
def list_receipts(db: DB, user: Reader):
    _staff(user)
    return receipt_out(db, service.list_receipts(db))


@router.post("/receipts", response_model=ReceiptOut, status_code=201)
def receive(data: ReceiptCreate, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_RECEIVE))]):
    receipt = service.receive_goods(
        db, user, warehouse_location_id=data.warehouse_location_id, purchase_order_id=data.purchase_order_id,
        supplier_reference=data.supplier_reference, notes=data.notes,
        lines=[ln.model_dump() for ln in data.lines],
    )
    db.commit()
    return receipt_out(db, [receipt])[0]


@router.get("/incoming", response_model=list[IncomingRow])
def incoming(db: DB, user: Reader):
    _staff(user)
    data = service.incoming_by_product(db)
    names = Names(db).add("product", *data.keys()).resolve()
    return [IncomingRow(product_id=pid, sku=names.sku(pid), product_name=names.product_name(pid), incoming_qty=q)
            for pid, q in sorted(data.items(), key=lambda kv: names.sku(kv[0]) or "")]
