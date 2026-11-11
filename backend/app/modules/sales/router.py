from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.lookups import Names
from app.core.permissions import P, role_has
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.replenishment.models import Delivery, DeliveryLine, ReplenishmentRequest
from app.modules.sales import service
from app.modules.sales.models import ConsignmentSale, InvoiceStatus
from app.modules.sales.schemas import (
    CashSaleCreate,
    LinkedDelivery,
    LinkedRequest,
    SaleCreate,
    SaleLineOut,
    SaleOut,
    SaleReversal,
)

router = APIRouter(prefix="/sales", tags=["sales"])
Reader = Annotated[User, Depends(require(P.INVENTORY_READ))]


INVOICE_STATE = {InvoiceStatus.DRAFTED: "INVOICE_DRAFTED", InvoiceStatus.INVOICED: "INVOICED"}


def sales_out(db, sales: list[ConsignmentSale], user: User) -> list[SaleOut]:
    """Billing visibility (D12): everyone sees whether a line is invoiced; the invoice number goes to RM/FM/Admin and
    to the dealer for their own sales; the Xero number only to RM/FM/Admin. Warehouse and reps see the state only."""
    from app.modules.invoicing.models import Invoice, InvoiceLine

    sees_refs = role_has(user.role, P.INVOICE_REFERENCE_READ)
    sees_number = sees_refs or user.is_reseller_user

    names = Names(db)
    line_ids = []
    for s in sales:
        names.add("reseller", s.reseller_id).add("location", s.location_id).add("user", s.recorded_by_user_id)
        names.add("product", *[ln.product_id for ln in s.lines])
        line_ids += [ln.id for ln in s.lines]
    names.resolve()
    reqs: dict[int, list[LinkedRequest]] = {}
    inv_numbers: dict[int, tuple[str, str | None, object]] = {}
    if line_ids:
        linked = list(db.execute(select(ReplenishmentRequest)
                                 .where(ReplenishmentRequest.sale_line_id.in_(line_ids))).scalars())
        shipments: dict[int, list[LinkedDelivery]] = {}
        if linked:
            for req_id, d in db.execute(
                select(DeliveryLine.request_id, Delivery).join(Delivery, Delivery.id == DeliveryLine.delivery_id)
                .where(DeliveryLine.request_id.in_([r.id for r in linked])).order_by(Delivery.id)
            ).tuples():
                shipments.setdefault(req_id, []).append(LinkedDelivery(
                    id=d.id, number=d.number, status=d.status, dispatched_at=d.dispatched_at, received_at=d.received_at))
        for r in linked:
            reqs.setdefault(r.sale_line_id, []).append(LinkedRequest(
                id=r.id, number=r.number, qty_required=r.qty_required, status=r.status, qty_in_transit=r.qty_in_transit,
                qty_delivered=r.qty_delivered, deliveries=shipments.get(r.id, [])))
        for sl_id, num, xero, issued in db.execute(
            select(InvoiceLine.sale_line_id, Invoice.number, Invoice.external_reference, Invoice.issued_at)
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .where(InvoiceLine.sale_line_id.in_(line_ids), InvoiceLine.is_active.is_(True))
        ).all():
            inv_numbers[sl_id] = (num, xero, issued)
    out = []
    for s in sales:
        lines = [
            SaleLineOut(
                id=ln.id, product_id=ln.product_id, sku=names.sku(ln.product_id),
                product_name=names.product_name(ln.product_id), quantity=ln.quantity, reversed_qty=ln.reversed_qty,
                chargeable_qty=ln.chargeable_qty, unit_price=ln.unit_price, price_source=ln.price_source,
                tax_code=ln.tax_code, tax_rate=ln.tax_rate,
                line_net=(ln.unit_price * ln.chargeable_qty).quantize(Decimal("0.01")),
                invoice_status=ln.invoice_status,
                invoice_number=inv_numbers.get(ln.id, (None, None, None))[0] if sees_number else None,
                replenishment=reqs.get(ln.id, []),
                invoice_state=INVOICE_STATE.get(ln.invoice_status, "NOT_INVOICED"),
                invoiced=ln.invoice_status == InvoiceStatus.INVOICED,
                xero_reference=inv_numbers.get(ln.id, (None, None, None))[1] if sees_refs else None,
                invoiced_at=inv_numbers.get(ln.id, (None, None, None))[2] if sees_number else None,
            )
            for ln in s.lines
        ]
        out.append(SaleOut(
            id=s.id, number=s.number, reseller_id=s.reseller_id, reseller_name=names.reseller_name(s.reseller_id),
            location_id=s.location_id, location_code=names.loc_code(s.location_id), sale_date=s.sale_date,
            source=s.source, source_reference=s.source_reference, stocktake_id=s.stocktake_id,
            recorded_by=names.user_name(s.recorded_by_user_id), recorded_at=s.recorded_at, notes=s.notes,
            customer_name=s.customer_name, customer_phone=s.customer_phone,
            total_qty=sum(ln.chargeable_qty for ln in lines), total_net=sum((ln.line_net for ln in lines), Decimal("0")),
            lines=lines,
        ))
    return out


@router.get("", response_model=list[SaleOut])
def list_sales(db: DB, user: Reader, reseller_id: int | None = None, location_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None,
               limit: Annotated[int, Query(ge=1, le=5000)] = 200):
    return sales_out(db, service.list_sales(db, user, reseller_id=reseller_id, location_id=location_id,
                                            date_from=date_from, date_to=date_to, limit=limit), user)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: DB, user: Reader):
    return sales_out(db, [service.get_sale(db, user, sale_id)], user)[0]


@router.post("/cash", response_model=SaleOut, status_code=201)
def record_cash_sale(data: CashSaleCreate, db: DB, user: Annotated[User, Depends(require(P.SALES_CASH))]):
    """Non-consignment sale from warehouse stock (CASH_SALE; D6): no replacement; an invoice record to complete in Xero."""
    sale, _ = service.record_cash_sale(
        db, user, sale_date=data.sale_date, customer_name=data.customer_name, customer_phone=data.customer_phone,
        notes=data.notes, lines=[service.SaleLineInput(product_id=ln.product_id, quantity=ln.quantity,
                                                       unit_price=ln.unit_price,
                                                       price_override_reason=ln.price_override_reason)
                                 for ln in data.lines])
    db.commit()
    return sales_out(db, [service.get_sale(db, user, sale.id)], user)[0]


@router.post("", response_model=SaleOut, status_code=201)
def record_sale(data: SaleCreate, db: DB, user: Annotated[User, Depends(require(P.SALES_RECORD))]):
    sale = service.record_sale(
        db, user, location_id=data.location_id, sale_date=data.sale_date, source=data.source,
        source_reference=data.source_reference, notes=data.notes,
        lines=[service.SaleLineInput(**ln.model_dump()) for ln in data.lines],
    )
    db.commit()
    return sales_out(db, [service.get_sale(db, user, sale.id)], user)[0]


@router.post("/lines/{line_id}/reverse", response_model=SaleOut)
def reverse(line_id: int, data: SaleReversal, db: DB, user: Annotated[User, Depends(require(P.SALES_REVERSE))]):
    line = service.reverse_sale_line(db, user, line_id, data.quantity, data.reason)
    db.commit()
    return sales_out(db, [service.get_sale(db, user, line.sale_id)], user)[0]
