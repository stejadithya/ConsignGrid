from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.customers.models import LocationType
from app.modules.inventory.models import Bucket, TxnType


class BalanceOut(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    location_type: LocationType
    reseller_id: int | None
    product_id: int
    sku: str
    product_name: str
    on_hand: int
    reserved: int
    blocked: int
    available: int


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    location_id: int
    bucket: Bucket
    quantity: int
    reservation_id: int | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    txn_type: TxnType
    occurred_at: datetime
    actor_user_id: int | None
    approved_by_user_id: int | None
    reference_type: str | None
    reference_id: int | None
    reference_number: str | None
    reason: str | None
    notes: str | None
    reverses_transaction_id: int | None
    entries: list[EntryOut]


class QtyLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100000)


class OpeningBalanceIn(BaseModel):
    location_id: int
    lines: list[QtyLine] = Field(min_length=1)
    notes: str | None = None


class AdjustmentIn(BaseModel):
    location_id: int
    product_id: int
    quantity_delta: int = Field(ne=0, ge=-100000, le=100000)
    reason: str = Field(min_length=3, max_length=500)


class StockStateChangeIn(BaseModel):
    location_id: int
    product_id: int
    quantity: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=3, max_length=500)


class ReconciliationRow(BaseModel):
    location_id: int
    product_id: int
    bucket: str
    ledger_qty: int
    balance_qty: int


class ReconciliationOut(BaseModel):
    balanced: bool
    checked_at: datetime
    differences: list[ReconciliationRow]
    unbalanced_transaction_ids: list[int]


class AvailabilityRow(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    location_type: LocationType
    reseller_id: int | None
    reseller_name: str | None
    reseller_status: str | None
    transfer_consent: str | None
    on_hand: int
    reserved: int
    blocked: int
    available: int


class ArrivalOut(BaseModel):
    on: datetime | date
    qty: int
    reason: str
    group: str
    reference: str | None


class InStockPart(BaseModel):
    label: str
    qty: int


class ProvenanceOut(BaseModel):
    location_id: int
    product_id: int
    on_hand: int
    arrivals: list[ArrivalOut]
    more: bool
    in_stock: list[InStockPart]


class AvailabilityCheckIn(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=200)
    dealer_location_id: int | None = None


class LocationStockOut(BaseModel):
    on_hand: int
    available: int


class OtherDealersOut(BaseModel):
    available: int
    locations: int


class AvailabilityCheckOut(BaseModel):
    product_id: int
    warehouse_available: int
    warehouse_on_hand: int
    at_this_location: LocationStockOut | None = None
    dealer_total_on_hand: int | None = None
    other_dealers: OtherDealersOut
