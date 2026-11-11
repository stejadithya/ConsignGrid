"""Invoices for confirmed consignment sales. Replenishment and transfers never reach this module."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.db import flush_or_conflict
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.numbering import next_number
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, Reseller
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.invoicing.integration import get_exporter, invoice_payload
from app.modules.invoicing.models import Invoice, InvoiceDocStatus, InvoiceLine
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine, InvoiceStatus

CENT = Decimal("0.01")


def _money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def uninvoiced_lines(db: Session, user: User, reseller_id: int | None = None):
    """Chargeable sale lines not on any invoice (UNINVOICED)."""
    stmt = (
        select(ConsignmentSaleLine, ConsignmentSale)
        .join(ConsignmentSale, ConsignmentSale.id == ConsignmentSaleLine.sale_id)
        .where(ConsignmentSaleLine.invoice_status == InvoiceStatus.UNINVOICED,
               ConsignmentSaleLine.quantity > ConsignmentSaleLine.reversed_qty)
    )
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(ConsignmentSale.reseller_id == restricted)
    if reseller_id is not None:
        stmt = stmt.where(ConsignmentSale.reseller_id == reseller_id)
    return db.execute(stmt.order_by(ConsignmentSale.sale_date, ConsignmentSaleLine.id)).tuples().all()


def get_invoice(db: Session, user: User, invoice_id: int, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.lines))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    inv = db.execute(stmt).scalar_one_or_none()
    if inv is None:
        raise NotFoundError("Invoice not found")
    ensure_reseller_access(user, inv.reseller_id, "Invoice")
    return inv


def create_invoice(db: Session, actor: User | None, *, reseller_id: int, sale_line_ids: list[int] | None = None,
                   invoice_date: date | None = None, notes: str | None = None) -> Invoice:
    reseller = db.get(Reseller, reseller_id)
    if reseller is None:
        raise NotFoundError("Dealer not found")
    if sale_line_ids is None:
        sale_line_ids = [ln.id for ln, _ in uninvoiced_lines(db, actor, reseller_id)]
    if not sale_line_ids:
        raise BusinessRuleError("There are no uninvoiced sales for this dealer")
    # Lock the sale lines: concurrent invoice runs cannot pick up the same line.
    lines = db.execute(
        select(ConsignmentSaleLine).where(ConsignmentSaleLine.id.in_(sale_line_ids))
        .order_by(ConsignmentSaleLine.id).with_for_update().execution_options(populate_existing=True)
    ).scalars().all()
    if len(lines) != len(set(sale_line_ids)):
        raise NotFoundError("One or more sale lines were not found")
    sales = {s.id: s for s in db.execute(
        select(ConsignmentSale).where(ConsignmentSale.id.in_({ln.sale_id for ln in lines}))).scalars()}
    for ln in lines:
        if sales[ln.sale_id].reseller_id != reseller.id:
            raise BusinessRuleError("All sale lines must belong to the invoiced dealer")
        if ln.invoice_status != InvoiceStatus.UNINVOICED or ln.chargeable_qty <= 0:
            raise ConflictError(f"Sale line {ln.id} ({sales[ln.sale_id].number}) is already {ln.invoice_status}")

    settings = get_settings()
    inv_date = invoice_date or date.today()
    terms = reseller.payment_terms_days if reseller.payment_terms_days is not None else settings.invoice_due_days_default
    inv = Invoice(
        number=next_number(db, "INV"), reseller_id=reseller.id, status=InvoiceDocStatus.DRAFT, invoice_date=inv_date,
        due_date=inv_date + timedelta(days=terms), currency=settings.default_currency,
        subtotal=Decimal("0"), tax_total=Decimal("0"), total=Decimal("0"),
        bill_to_name=reseller.business_name, bill_to_account_ref=reseller.account_ref,
        bill_to_address=reseller.billing_address, bill_to_tax_number=reseller.tax_number,
        notes=notes, created_by_user_id=actor.id if actor else None,   # None: created by the system itself
    )
    db.add(inv)
    db.flush()
    subtotal = tax_total = Decimal("0")
    for ln in lines:
        sale = sales[ln.sale_id]
        product = db.get(Product, ln.product_id)
        loc = db.get(Location, sale.location_id)
        net = _money(ln.unit_price * ln.chargeable_qty)
        tax = _money(net * ln.tax_rate)
        db.add(InvoiceLine(
            invoice_id=inv.id, sale_line_id=ln.id, sale_number=sale.number, sale_date=sale.sale_date,
            location_code=loc.code, sku=product.sku, description=product.display_name[:300],
            quantity=ln.chargeable_qty, unit_price=ln.unit_price, tax_code=ln.tax_code, tax_rate=ln.tax_rate,
            line_net=net, line_tax=tax, line_total=net + tax, is_active=True,
        ))
        ln.invoice_status = InvoiceStatus.DRAFTED
        subtotal += net
        tax_total += tax
    inv.subtotal, inv.tax_total, inv.total = subtotal, tax_total, subtotal + tax_total
    # The partial unique index on invoice_lines(sale_line_id) WHERE is_active is the final guard.
    flush_or_conflict(db, None, "One or more sale lines are already on another invoice")
    record_audit(db, actor_id=actor.id if actor else None, action="invoice.create", entity_type="invoice",
                 entity_id=inv.id,
                 reseller_id=reseller.id,
                 summary=f"Drafted {inv.number} for {reseller.account_ref}: {len(lines)} line(s), "
                         f"{sum(ln.chargeable_qty for ln in lines)} tyre(s)")
    db.refresh(inv)
    return inv


def issue(db: Session, actor: User, invoice_id: int, xero_reference: str) -> Invoice:
    """Mark an invoice record as invoiced in Xero: the Xero invoice number is required (finding 24)."""
    inv = get_invoice(db, actor, invoice_id, lock=True)
    if inv.status != InvoiceDocStatus.DRAFT:
        raise ConflictError(f"{inv.number} is {inv.status}")
    xero_reference = xero_reference.strip()
    if not xero_reference:
        raise BusinessRuleError("Enter the Xero invoice number")
    ids = [ln.sale_line_id for ln in inv.lines if ln.is_active]
    for sl in db.execute(select(ConsignmentSaleLine).where(ConsignmentSaleLine.id.in_(ids)).with_for_update()).scalars():
        sl.invoice_status = InvoiceStatus.INVOICED
    inv.status = InvoiceDocStatus.ISSUED
    inv.issued_by_user_id = actor.id
    inv.issued_at = datetime.now(UTC)
    inv.external_reference = xero_reference
    inv.xero_recorded_by_user_id, inv.xero_recorded_at = actor.id, inv.issued_at
    db.flush()
    record_audit(db, actor_id=actor.id, action="invoice.issue", entity_type="invoice", entity_id=inv.id,
                 reseller_id=inv.reseller_id,
                 summary=f"Invoiced {inv.number} in Xero as {xero_reference} "
                         f"({sum(ln.quantity for ln in inv.lines if ln.is_active)} tyre(s))",
                 details={"xero_reference": xero_reference})
    return inv


def void(db: Session, actor: User, invoice_id: int, reason: str) -> Invoice:
    inv = get_invoice(db, actor, invoice_id, lock=True)
    if inv.status == InvoiceDocStatus.VOID:
        raise ConflictError(f"{inv.number} is already void")
    ids = [ln.sale_line_id for ln in inv.lines if ln.is_active]
    for ln in inv.lines:
        ln.is_active = False
    for sl in db.execute(select(ConsignmentSaleLine).where(ConsignmentSaleLine.id.in_(ids)).with_for_update()).scalars():
        sl.invoice_status = InvoiceStatus.UNINVOICED
    previous = inv.status
    inv.status = InvoiceDocStatus.VOID
    inv.voided_by_user_id = actor.id
    inv.voided_at = datetime.now(UTC)
    inv.void_reason = reason
    db.flush()
    record_audit(db, actor_id=actor.id, action="invoice.void", entity_type="invoice", entity_id=inv.id,
                 reseller_id=inv.reseller_id,
                 summary=f"Voided {inv.number} (was {previous}): {reason}; {len(ids)} sale line(s) released")
    return inv


def export(db: Session, actor: User, invoice_id: int) -> dict:
    inv = get_invoice(db, actor, invoice_id, lock=True)
    if inv.status != InvoiceDocStatus.ISSUED:
        raise ConflictError("Only issued invoices can be exported")
    payload = invoice_payload(inv)
    external_id = get_exporter().export(payload)
    if external_id:
        inv.external_reference = external_id
    inv.exported_at = datetime.now(UTC)
    record_audit(db, actor_id=actor.id, action="invoice.export", entity_type="invoice", entity_id=inv.id,
                 reseller_id=inv.reseller_id, summary=f"Exported {inv.number} via {get_exporter().name}")
    return payload


def set_external_reference(db: Session, actor: User, invoice_id: int, reference: str) -> Invoice:
    inv = get_invoice(db, actor, invoice_id, lock=True)
    if inv.status != InvoiceDocStatus.ISSUED:
        raise ConflictError("Only issued invoices carry an accounting reference")
    previous = inv.external_reference
    inv.external_reference = reference.strip()
    inv.xero_recorded_by_user_id, inv.xero_recorded_at = actor.id, datetime.now(UTC)
    record_audit(db, actor_id=actor.id, action="invoice.external_ref", entity_type="invoice", entity_id=inv.id,
                 reseller_id=inv.reseller_id,
                 summary=f"{inv.number} Xero number set to {inv.external_reference}"
                         + (f" (was {previous})" if previous and previous != inv.external_reference else ""),
                 details={"previous": previous, "xero_reference": inv.external_reference})
    return inv


def list_invoices(db: Session, user: User, *, reseller_id: int | None = None,
                  status: InvoiceDocStatus | None = None, limit: int = 200) -> list[Invoice]:
    stmt = select(Invoice).options(selectinload(Invoice.lines))
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Invoice.reseller_id == restricted)
    if reseller_id is not None:
        stmt = stmt.where(Invoice.reseller_id == reseller_id)
    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    return list(db.execute(stmt.order_by(Invoice.id.desc()).limit(limit)).scalars())
