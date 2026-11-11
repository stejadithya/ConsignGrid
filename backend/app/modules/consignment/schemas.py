from pydantic import BaseModel, ConfigDict, Field, model_validator


class AllocationIn(BaseModel):
    location_id: int
    product_id: int
    target_qty: int = Field(ge=0, le=100000)
    min_qty: int | None = Field(default=None, ge=0)
    max_qty: int | None = Field(default=None, ge=0)
    auto_replenish: bool | None = None  # defaults to the agreement's auto_replenish_default
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def _check(self):
        if self.max_qty is not None and self.max_qty < self.target_qty:
            raise ValueError("max_qty must be at least target_qty")
        if self.min_qty is not None and self.min_qty > self.target_qty:
            raise ValueError("min_qty cannot exceed target_qty")
        return self


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    product_id: int
    target_qty: int
    min_qty: int | None
    max_qty: int | None
    auto_replenish: bool
    is_active: bool


class AllocationPosition(BaseModel):
    """Target vs actual for one reseller location + SKU."""

    allocation_id: int | None
    location_id: int
    location_code: str
    reseller_id: int
    product_id: int
    sku: str
    product_name: str
    target_qty: int
    auto_replenish: bool
    on_hand: int
    reserved: int
    blocked: int
    available: int
    open_replenishment: int      # outstanding on open requests (incl. allocated/in transit)
    replenishment_in_transit: int
    transfers_inbound: int       # open inbound transfers (approved or in transit)
    remaining_unmet: int         # shortfall not yet covered by any open demand


class AllocationChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_target_qty: int | None
    new_target_qty: int
    old_auto_replenish: bool | None
    new_auto_replenish: bool
    reason: str
    changed_by_user_id: int | None
    changed_at: object
