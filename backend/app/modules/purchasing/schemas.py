from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.purchasing.models import POStatus


class POLineIn(BaseModel):
    product_id: int
    qty_ordered: int = Field(gt=0, le=100000)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class POCreate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    supplier_reference: str | None = Field(default=None, max_length=100)
    warehouse_location_id: int
    expected_date: date | None = None
    notes: str | None = None
    lines: list[POLineIn] = Field(min_length=1)


class POLineOut(BaseModel):
    id: int
    product_id: int
    sku: str | None
    product_name: str | None
    qty_ordered: int
    qty_received: int
    qty_outstanding: int
    unit_cost: Decimal | None


class POOut(BaseModel):
    id: int
    number: str
    supplier_name: str
    supplier_reference: str | None
    warehouse_location_id: int
    warehouse_code: str | None
    expected_date: date | None
    status: POStatus
    notes: str | None
    created_at: datetime
    lines: list[POLineOut]


class ReceiptLineIn(BaseModel):
    product_id: int | None = None
    purchase_order_line_id: int | None = None
    qty_received: int = Field(gt=0, le=100000)
    qty_damaged: int = Field(default=0, ge=0)


class ReceiptCreate(BaseModel):
    warehouse_location_id: int
    purchase_order_id: int | None = None
    supplier_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    lines: list[ReceiptLineIn] = Field(min_length=1)


class ReceiptLineOut(BaseModel):
    id: int
    product_id: int
    sku: str | None
    purchase_order_line_id: int | None
    qty_received: int
    qty_damaged: int


class ReceiptOut(BaseModel):
    id: int
    number: str
    purchase_order_id: int | None
    warehouse_location_id: int
    supplier_reference: str | None
    received_at: datetime
    received_by: str | None
    inventory_transaction_id: int | None
    notes: str | None
    lines: list[ReceiptLineOut]
    open_backorders_for_received_skus: int = 0


class IncomingRow(BaseModel):
    product_id: int
    sku: str | None
    product_name: str | None
    incoming_qty: int
