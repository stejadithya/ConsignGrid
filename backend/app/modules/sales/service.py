"""Confirmed consignment sales. A sale reduces unsold stock, becomes chargeable, and triggers replenishment."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.numbering import next_number
from app.core.permissions import ROLE_LABELS, Role
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product, TaxRate
from app.modules.catalogue.service import default_tax_rate
from app.modules.customers.models import Location, LocationType, Reseller, ResellerStatus
from app.modules.customers.service import effective_price
from app.modules.identity.models import User
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.inventory.models import TxnType
from app.modules.inventory.service import Ledger, Ref, default_warehouse, system_location
from app.modules.invoicing import service as invoicing
from app.modules.notifications.service import notify_users, staff_in_roles
from app.modules.replenishment import service as replenishment
from app.modules.replenishment.models import ReplenishmentRequest
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine, InvoiceStatus, SaleSource

# Sales of tyres without a price snapshot 0.00: the platform counts units; the accounting system holds the prices (D2).
NOT_PRICED = Decimal("0.00")


@dataclass
class SaleLineInput:
    product_id: int
    quantity: int
    unit_price: Decimal | None = None       # manual override
    price_override_reason: str | None = None


def _tax_for(db: Session, reseller: Reseller) -> TaxRate:
    rate = db.get(TaxRate, reseller.tax_rate_id) if reseller.tax_rate_id else default_tax_rate(db)
    if rate is None:
        raise BusinessRuleError("No tax rate is configured. Set a default tax rate before recording sales.")
    return rate


def record_sale(
    db: Session, actor: User | None, *, location_id: int, sale_date: date, source: SaleSource,
    lines: list[SaleLineInput], source_reference: str | None = None, notes: str | None = None,
    stocktake_id: int | None = None,
) -> ConsignmentSale:
    if source == SaleSource.CASH_SALE:
        raise BusinessRuleError("Record sales from the warehouse with 'Non-consignment sale (from warehouse)'")
    location = db.get(Location, location_id)
    if location is None or location.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError("Sales are recorded against a dealer consignment location")
    # Reseller users may only report sales for their own locations, at agreed prices (no manual overrides).
    # actor None: recorded by the system itself (a stock check invoiced automatically, release 1.11).
    if actor is not None:
        ensure_reseller_access(actor, location.reseller_id, "Location")
    if actor is not None and actor.is_reseller_user:
        # Besides reporting their own sales, a reseller confirms stock-check shortages as sold (P-018).
        allowed = {SaleSource.RESELLER_REPORT} | ({SaleSource.STOCKTAKE} if stocktake_id is not None else set())
        if source not in allowed:
            raise BusinessRuleError("Dealer users report sales with source 'Reported by dealer'")
        if any(ln.unit_price is not None for ln in lines):
            raise BusinessRuleError("Dealer users cannot override the agreed price")
    reseller = db.get(Reseller, location.reseller_id)
    if reseller.status == ResellerStatus.CLOSED:
        raise BusinessRuleError(f"Dealer {reseller.account_ref} is closed")
    if sale_date > date.today():
        raise BusinessRuleError("Sale date cannot be in the future")
    if not lines:
        raise BusinessRuleError("A sale needs at least one line")
    if len({ln.product_id for ln in lines}) != len(lines):
        raise BusinessRuleError("Each product may appear only once per sale")

    tax = _tax_for(db, reseller)
    sale = ConsignmentSale(number=next_number(db, "SAL"), reseller_id=reseller.id, location_id=location.id,
                           sale_date=sale_date, source=source, source_reference=source_reference, notes=notes,
                           stocktake_id=stocktake_id, recorded_by_user_id=actor.id if actor else None)
    db.add(sale)
    db.flush()
    ref = Ref("consignment_sale", sale.id, sale.number)
    ledger = Ledger(db, TxnType.CONSIGNMENT_SALE, actor_id=actor.id if actor else None, ref=ref, notes=notes)
    sale.inventory_transaction_id = ledger.txn.id
    sold = system_location(db, LocationType.SOLD)

    created_lines = []
    for ln in lines:
        product = db.get(Product, ln.product_id)
        if product is None:
            raise NotFoundError(f"Product {ln.product_id} not found")
        if ln.quantity <= 0:
            raise BusinessRuleError("Quantity must be positive")
        if ln.unit_price is not None:
            if not ln.price_override_reason:
                raise BusinessRuleError(f"A reason is required to override the price of {product.tyre_label}")
            price, price_source = ln.unit_price, "MANUAL"
        else:
            price, price_source = effective_price(db, reseller.id, product, sale_date)
            if price is None:   # prices are managed in Xero (D2): record the sale without one
                price, price_source = NOT_PRICED, "NOT_PRICED"
        # Stock leaves the reseller's *available* consignment stock (not reserved/blocked).
        ledger.move(product.id, location, sold, ln.quantity)
        line = ConsignmentSaleLine(sale_id=sale.id, product_id=product.id, quantity=ln.quantity, unit_price=price,
                                   price_source=price_source, price_override_reason=ln.price_override_reason,
                                   tax_rate_id=tax.id, tax_code=tax.code, tax_rate=tax.rate,
                                   invoice_status=InvoiceStatus.UNINVOICED)
        db.add(line)
        db.flush()
        created_lines.append(line)

    raised = []
    for line in created_lines:
        req = replenishment.request_for_sale(db, actor.id if actor else None, location=location, product_id=line.product_id,
                                             sold_qty=line.quantity, sale_line_id=line.id, origin=ref)
        if req is not None:
            raised.append(req)
    if raised:
        _notify_replacements(db, actor, reseller, sale, raised)

    record_audit(db, actor_id=actor.id if actor else None, action="sale.record", entity_type="consignment_sale",
                 entity_id=sale.id,
                 reseller_id=reseller.id,
                 summary=f"Recorded {sale.number} at {location.code}: {sum(ln.quantity for ln in lines)} units ({source})")
    db.refresh(sale)
    return sale


CASH_ACCOUNT_REF = "CASH"


def cash_account(db: Session) -> Reseller:
    """The system account that groups walk-in cash sales (created on first use, hidden from reseller lists)."""
    acct = db.execute(select(Reseller).where(Reseller.is_cash_account.is_(True))).scalar_one_or_none()
    if acct is None:
        acct = Reseller(account_ref=CASH_ACCOUNT_REF, business_name="Cash sales (walk-in)", status=ResellerStatus.ACTIVE,
                        is_cash_account=True, payment_terms_days=0,
                        notes="System account for warehouse cash sales. Not a consignment dealer.")
        db.add(acct)
        db.flush()
    return acct


def record_cash_sale(db: Session, actor: User, *, sale_date: date, lines: list[SaleLineInput],
                     customer_name: str | None = None, customer_phone: str | None = None,
                     notes: str | None = None) -> tuple[ConsignmentSale, object]:
    """A walk-in customer (nearby shop, any reseller) buys and pays at the warehouse.

    Stock leaves the default warehouse straight away (available stock only), the sale is chargeable at the dealer
    price unless overridden with a reason, no replacement is raised, and an invoice record is created for the customer.
    """
    if sale_date > date.today():
        raise BusinessRuleError("Sale date cannot be in the future")
    if not lines:
        raise BusinessRuleError("A sale needs at least one line")
    if len({ln.product_id for ln in lines}) != len(lines):
        raise BusinessRuleError("Each product may appear only once per sale")
    account = cash_account(db)
    warehouse = default_warehouse(db)
    tax = _tax_for(db, account)
    name = (customer_name or "").strip() or None
    sale = ConsignmentSale(number=next_number(db, "SAL"), reseller_id=account.id, location_id=warehouse.id,
                           sale_date=sale_date, source=SaleSource.CASH_SALE, source_reference=name, notes=notes,
                           recorded_by_user_id=actor.id, customer_name=name,
                           customer_phone=(customer_phone or "").strip() or None)
    db.add(sale)
    db.flush()
    ledger = Ledger(db, TxnType.CONSIGNMENT_SALE, actor_id=actor.id, ref=Ref("consignment_sale", sale.id, sale.number),
                    notes=f"Non-consignment sale{' to ' + name if name else ''}")
    sale.inventory_transaction_id = ledger.txn.id
    sold = system_location(db, LocationType.SOLD)
    line_ids = []
    for ln in lines:
        product = db.get(Product, ln.product_id)
        if product is None:
            raise NotFoundError(f"Product {ln.product_id} not found")
        if ln.quantity <= 0:
            raise BusinessRuleError("Quantity must be positive")
        if ln.unit_price is not None:
            if not ln.price_override_reason:
                raise BusinessRuleError(f"A reason is required to override the price of {product.tyre_label}")
            price, price_source = ln.unit_price, "MANUAL"
        else:
            if product.list_price is None:   # prices are managed in Xero (D2)
                price, price_source = NOT_PRICED, "NOT_PRICED"
            else:
                price, price_source = product.list_price, "LIST"
        ledger.move(product.id, warehouse, sold, ln.quantity)
        line = ConsignmentSaleLine(sale_id=sale.id, product_id=product.id, quantity=ln.quantity, unit_price=price,
                                   price_source=price_source, price_override_reason=ln.price_override_reason,
                                   tax_rate_id=tax.id, tax_code=tax.code, tax_rate=tax.rate,
                                   invoice_status=InvoiceStatus.UNINVOICED)
        db.add(line)
        db.flush()
        line_ids.append(line.id)
    invoice = invoicing.create_invoice(db, actor, reseller_id=account.id, sale_line_ids=line_ids,
                                       notes=f"Non-consignment sale {sale.number} (from warehouse)")
    invoice.bill_to_name = name or "Cash customer"
    invoice.bill_to_account_ref = CASH_ACCOUNT_REF
    invoice.bill_to_address = sale.customer_phone
    record_audit(db, actor_id=actor.id, action="sale.cash", entity_type="consignment_sale", entity_id=sale.id,
                 summary=f"Non-consignment sale {sale.number} from {warehouse.code}: {sum(ln.quantity for ln in lines)} units"
                         f"{' to ' + name if name else ''}; invoice record {invoice.number}")
    db.refresh(sale)
    return sale, invoice


def _notify_replacements(db: Session, actor: User | None, reseller: Reseller, sale: ConsignmentSale,
                         raised: list[ReplenishmentRequest]) -> None:
    """Tell the warehouse, relationship managers and the reseller's sales rep that replacements were raised."""
    skus = {p.id: p.tyre_label for p in db.execute(
        select(Product).where(Product.id.in_([r.product_id for r in raised]))).scalars()}
    who = (f"{actor.full_name} ({ROLE_LABELS[Role(actor.role)]})" if actor
           else f"{get_settings().app_display_name} (automatically)")
    detail = ", ".join(f"{r.qty_required} × {skus.get(r.product_id)} ({r.number})" for r in raised)
    recipients = [*staff_in_roles(db, Role.WAREHOUSE_MANAGER, Role.RELATIONSHIP_MANAGER), reseller.sales_rep_user_id]
    title = f"Replacement raised for {reseller.business_name}"
    body = f"{who} recorded sale {sale.number}; replacement to pick and dispatch: {detail}"
    link = f"/replenishment/{raised[0].id}" if len(raised) == 1 else "/replenishment"
    notify_users(db, recipients, title, body, link=link, entity_type="consignment_sale", entity_id=sale.id,
                 exclude=actor.id if actor else None)


def get_sale(db: Session, user: User, sale_id: int) -> ConsignmentSale:
    sale = db.execute(
        select(ConsignmentSale).where(ConsignmentSale.id == sale_id).options(selectinload(ConsignmentSale.lines))
    ).scalar_one_or_none()
    if sale is None:
        raise NotFoundError("Sale not found")
    ensure_reseller_access(user, sale.reseller_id, "Sale")
    return sale


def list_sales(db: Session, user: User, *, reseller_id: int | None = None, location_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None, limit: int = 200) -> list[ConsignmentSale]:
    stmt = select(ConsignmentSale).options(selectinload(ConsignmentSale.lines))
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(ConsignmentSale.reseller_id == restricted)
    if reseller_id is not None:
        stmt = stmt.where(ConsignmentSale.reseller_id == reseller_id)
    if location_id is not None:
        stmt = stmt.where(ConsignmentSale.location_id == location_id)
    if date_from:
        stmt = stmt.where(ConsignmentSale.sale_date >= date_from)
    if date_to:
        stmt = stmt.where(ConsignmentSale.sale_date <= date_to)
    return list(db.execute(stmt.order_by(ConsignmentSale.id.desc()).limit(limit)).scalars())


def reverse_sale_line(db: Session, actor: User, sale_line_id: int, qty: int, reason: str) -> ConsignmentSaleLine:
    """Controlled correction of an uninvoiced sale line (A-010). Posts a compensating movement."""
    line = db.execute(
        select(ConsignmentSaleLine).where(ConsignmentSaleLine.id == sale_line_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if line is None:
        raise NotFoundError("Sale line not found")
    if line.invoice_status != InvoiceStatus.UNINVOICED:
        raise ConflictError(
            f"Sale line is {line.invoice_status}; void the invoice first (credit notes are not yet supported)"
        )
    if qty <= 0 or qty > line.chargeable_qty:
        raise BusinessRuleError(f"Can reverse at most {line.chargeable_qty}")
    sale = db.get(ConsignmentSale, line.sale_id)
    location = db.get(Location, sale.location_id)
    ref = Ref("consignment_sale", sale.id, sale.number)
    ledger = Ledger(db, TxnType.SALE_REVERSAL, actor_id=actor.id, approved_by_id=actor.id, ref=ref, reason=reason,
                    reverses_transaction_id=sale.inventory_transaction_id)
    ledger.move(line.product_id, system_location(db, LocationType.SOLD), location, qty)
    line.reversed_qty += qty
    if line.chargeable_qty == 0:
        line.invoice_status = InvoiceStatus.NOT_CHARGEABLE

    # The reseller has the stock back: withdraw the matching not-yet-dispatched replacement.
    remaining = qty
    for req in db.execute(
        select(ReplenishmentRequest).where(ReplenishmentRequest.sale_line_id == line.id)
        .order_by(ReplenishmentRequest.id)
    ).scalars():
        if remaining <= 0:
            break
        remaining -= replenishment.cancel_open_quantity(
            db, actor.id, req, remaining, f"Sale reversal: {reason}", ref, release_allocations=True)
    db.flush()
    record_audit(db, actor_id=actor.id, action="sale.reverse", entity_type="consignment_sale", entity_id=sale.id,
                 reseller_id=sale.reseller_id, summary=f"Reversed {qty} on {sale.number} line {line.id}: {reason}")
    return line
