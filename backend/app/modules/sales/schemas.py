from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.sales.models import InvoiceStatus, SaleSource


class SaleLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price_override_reason: str | None = Field(default=None, max_length=500)


class SaleCreate(BaseModel):
    location_id: int
    sale_date: date
    source: SaleSource = SaleSource.RESELLER_REPORT
    source_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    lines: list[SaleLineIn] = Field(min_length=1)


class CashSaleLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000)
    unit_price: Decimal | None = Field(default=None, ge=0)   # default: dealer price
    price_override_reason: str | None = Field(default=None, max_length=500)


class CashSaleCreate(BaseModel):
    sale_date: date
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    lines: list[CashSaleLineIn] = Field(min_length=1)


class SaleReversal(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class LinkedDelivery(BaseModel):
    id: int
    number: str
    status: str
    dispatched_at: datetime
    received_at: datetime | None = None


class LinkedRequest(BaseModel):
    id: int
    number: str
    qty_required: int
    status: str
    qty_in_transit: int = 0
    qty_delivered: int = 0
    deliveries: list[LinkedDelivery] = []   # the replacement's shipments (record-sale journey, finding 25)


class SaleLineOut(BaseModel):
    id: int
    product_id: int
    sku: str | None
    product_name: str | None
    quantity: int
    reversed_qty: int
    chargeable_qty: int
    unit_price: Decimal
    price_source: str
    tax_code: str
    tax_rate: Decimal
    line_net: Decimal
    invoice_status: InvoiceStatus
    invoice_number: str | None = None      # RM/FM/Admin, and the dealer for their own sales (D12)
    replenishment: list[LinkedRequest] = []
    invoice_state: str = "NOT_INVOICED"    # NOT_INVOICED | INVOICE_DRAFTED | INVOICED: everyone who sees the sale
    invoiced: bool = False
    xero_reference: str | None = None      # RM/FM/Admin only (INVOICE_REFERENCE_READ)
    invoiced_at: datetime | None = None    # when it was marked invoiced in Xero; same audience as invoice_number


class SaleOut(BaseModel):
    id: int
    number: str
    reseller_id: int
    reseller_name: str | None
    location_id: int
    location_code: str | None
    sale_date: date
    source: SaleSource
    source_reference: str | None
    stocktake_id: int | None
    recorded_by: str | None
    recorded_at: datetime
    notes: str | None
    total_qty: int
    total_net: Decimal
    lines: list[SaleLineOut]
    customer_name: str | None = None
    customer_phone: str | None = None
