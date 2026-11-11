from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.lookups import Names
from app.core.permissions import P, role_has
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.invoicing import service
from app.modules.invoicing.models import Invoice, InvoiceDocStatus

router = APIRouter(prefix="/invoices", tags=["invoicing"])
Reader = Annotated[User, Depends(require(P.INVOICE_READ))]
Creator = Annotated[User, Depends(require(P.INVOICE_CREATE))]


class InvoiceCreate(BaseModel):
    reseller_id: int
    sale_line_ids: list[int] | None = None
    invoice_date: date | None = None
    notes: str | None = None


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class IssueIn(BaseModel):
    xero_reference: str = Field(min_length=1, max_length=100)   # the invoice number in Xero


class ExternalRefIn(BaseModel):
    external_reference: str = Field(min_length=1, max_length=100)


class InvoiceLineOut(BaseModel):
    id: int
    sale_line_id: int
    sale_number: str
    sale_date: date
    location_code: str
    sku: str
    description: str
    quantity: int
    unit_price: Decimal
    tax_code: str
    tax_rate: Decimal
    line_net: Decimal
    line_tax: Decimal
    line_total: Decimal
    is_active: bool


class InvoiceOut(BaseModel):
    id: int
    number: str
    reseller_id: int
    status: InvoiceDocStatus
    invoice_date: date
    due_date: date
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    bill_to_name: str
    bill_to_account_ref: str
    bill_to_address: str | None
    bill_to_tax_number: str | None
    issuer_name: str
    issuer_details: str
    external_reference: str | None
    exported_at: datetime | None
    notes: str | None
    created_by: str | None
    created_at: datetime
    issued_by: str | None
    issued_at: datetime | None
    voided_by: str | None
    voided_at: datetime | None
    void_reason: str | None
    lines: list[InvoiceLineOut]
    xero_reference: str | None = None       # same as external_reference (release 1.11 name)
    xero_recorded_by: str | None = None
    xero_recorded_at: datetime | None = None


class UninvoicedOut(BaseModel):
    sale_line_id: int
    sale_id: int
    sale_number: str
    sale_date: date
    reseller_id: int
    reseller_name: str | None
    location_code: str | None
    product_id: int
    sku: str | None
    quantity: int
    unit_price: Decimal
    tax_code: str
    line_net: Decimal
    age_days: int


def invoices_out(db, invs: list[Invoice], user: User) -> list[InvoiceOut]:
    """The Xero number goes only to RM/FM/Admin (D12); dealers see their invoice records without it."""
    s = get_settings()
    sees_refs = role_has(user.role, P.INVOICE_REFERENCE_READ)
    names = Names(db)
    for i in invs:
        names.add("user", i.created_by_user_id, i.issued_by_user_id, i.voided_by_user_id, i.xero_recorded_by_user_id)
    names.resolve()
    return [
        InvoiceOut(
            id=i.id, number=i.number, reseller_id=i.reseller_id, status=i.status, invoice_date=i.invoice_date,
            due_date=i.due_date, currency=i.currency, subtotal=i.subtotal, tax_total=i.tax_total, total=i.total,
            bill_to_name=i.bill_to_name, bill_to_account_ref=i.bill_to_account_ref, bill_to_address=i.bill_to_address,
            bill_to_tax_number=i.bill_to_tax_number, issuer_name=s.invoice_issuer_name,
            issuer_details=s.invoice_issuer_details, external_reference=i.external_reference if sees_refs else None,
            exported_at=i.exported_at, notes=i.notes, created_by=names.user_name(i.created_by_user_id),
            created_at=i.created_at, issued_by=names.user_name(i.issued_by_user_id), issued_at=i.issued_at,
            voided_by=names.user_name(i.voided_by_user_id), voided_at=i.voided_at, void_reason=i.void_reason,
            lines=[InvoiceLineOut.model_validate(ln, from_attributes=True) for ln in i.lines],
            xero_reference=i.external_reference if sees_refs else None,
            xero_recorded_by=names.user_name(i.xero_recorded_by_user_id) if sees_refs else None,
            xero_recorded_at=i.xero_recorded_at if sees_refs else None,
        )
        for i in invs
    ]


@router.get("", response_model=list[InvoiceOut])
def list_invoices(db: DB, user: Reader, reseller_id: int | None = None, status: InvoiceDocStatus | None = None):
    return invoices_out(db, service.list_invoices(db, user, reseller_id=reseller_id, status=status), user)


@router.get("/uninvoiced", response_model=list[UninvoicedOut])
def uninvoiced(db: DB, user: Reader, reseller_id: int | None = None):
    rows = service.uninvoiced_lines(db, user, reseller_id)
    names = Names(db)
    for ln, sale in rows:
        names.add("reseller", sale.reseller_id).add("location", sale.location_id).add("product", ln.product_id)
    names.resolve()
    today = date.today()
    return [UninvoicedOut(
        sale_line_id=ln.id, sale_id=sale.id, sale_number=sale.number, sale_date=sale.sale_date,
        reseller_id=sale.reseller_id, reseller_name=names.reseller_name(sale.reseller_id),
        location_code=names.loc_code(sale.location_id), product_id=ln.product_id, sku=names.sku(ln.product_id),
        quantity=ln.chargeable_qty, unit_price=ln.unit_price, tax_code=ln.tax_code,
        line_net=(ln.unit_price * ln.chargeable_qty).quantize(Decimal("0.01")),
        age_days=(today - sale.sale_date).days,
    ) for ln, sale in rows]


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: DB, user: Reader):
    return invoices_out(db, [service.get_invoice(db, user, invoice_id)], user)[0]


@router.post("", response_model=InvoiceOut, status_code=201)
def create(data: InvoiceCreate, db: DB, user: Creator):
    inv = service.create_invoice(db, user, reseller_id=data.reseller_id, sale_line_ids=data.sale_line_ids,
                                 invoice_date=data.invoice_date, notes=data.notes)
    db.commit()
    return invoices_out(db, [service.get_invoice(db, user, inv.id)], user)[0]


@router.post("/{invoice_id}/issue", response_model=InvoiceOut)
def issue(invoice_id: int, data: IssueIn, db: DB, user: Creator):
    """Mark as invoiced in Xero, with the Xero invoice number."""
    service.issue(db, user, invoice_id, data.xero_reference)
    db.commit()
    return invoices_out(db, [service.get_invoice(db, user, invoice_id)], user)[0]


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
def void(invoice_id: int, data: VoidIn, db: DB, user: Annotated[User, Depends(require(P.INVOICE_VOID))]):
    service.void(db, user, invoice_id, data.reason)
    db.commit()
    return invoices_out(db, [service.get_invoice(db, user, invoice_id)], user)[0]


@router.post("/{invoice_id}/export")
def export(invoice_id: int, db: DB, user: Creator):
    payload = service.export(db, user, invoice_id)
    db.commit()
    return payload


@router.put("/{invoice_id}/external-reference", response_model=InvoiceOut)
def external_reference(invoice_id: int, data: ExternalRefIn, db: DB, user: Creator):
    service.set_external_reference(db, user, invoice_id, data.external_reference)
    db.commit()
    return invoices_out(db, [service.get_invoice(db, user, invoice_id)], user)[0]
