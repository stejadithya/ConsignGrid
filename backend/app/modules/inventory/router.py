from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import P
from app.modules.customers.models import LocationType
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User
from app.modules.inventory import availability as availability_check_service
from app.modules.inventory import operations as ops
from app.modules.inventory.models import InventoryTransaction, TxnType
from app.modules.inventory.provenance import provenance as stock_provenance
from app.modules.inventory.schemas import (
    AdjustmentIn,
    AvailabilityCheckIn,
    AvailabilityCheckOut,
    AvailabilityRow,
    BalanceOut,
    OpeningBalanceIn,
    ProvenanceOut,
    ReconciliationOut,
    ReconciliationRow,
    StockStateChangeIn,
    TransactionOut,
)
from app.modules.inventory.service import reconcile, unbalanced_transactions

router = APIRouter(prefix="/inventory", tags=["inventory"])

Reader = Annotated[User, Depends(require(P.INVENTORY_READ))]


@router.post("/availability-check", response_model=list[AvailabilityCheckOut])
def availability_check(data: AvailabilityCheckIn, db: DB, user: Reader):
    """For the tyres on a request: warehouse stock, what this dealer already holds, what other dealers could spare.
    Staff only: dealers never see warehouse figures or other dealers."""
    if user.is_reseller_user:
        raise PermissionDeniedError("Not available to dealer users")
    rows = availability_check_service.check(db, data.product_ids, data.dealer_location_id)
    return [AvailabilityCheckOut(**a.__dict__) for a in rows]


def _staff_only(user: User) -> None:
    if user.is_reseller_user:
        raise PermissionDeniedError("Not available to dealer users")


@router.get("/balances", response_model=list[BalanceOut])
def balances(
    db: DB, user: Reader, location_id: int | None = None, product_id: int | None = None,
    location_type: LocationType | None = None, reseller_id: int | None = None, include_zero: bool = False,
):
    return ops.list_balances(db, user, location_id=location_id, product_id=product_id,
                             location_type=location_type, reseller_id=reseller_id, include_zero=include_zero)


@router.get("/availability/{product_id}", response_model=list[AvailabilityRow])
def availability(product_id: int, db: DB, user: Reader):
    _staff_only(user)
    return ops.availability_by_product(db, product_id)


@router.get("/provenance", response_model=ProvenanceOut)
def provenance(location_id: int, product_id: int, db: DB, user: Reader):
    """Where this tyre at this location came from (the ⓘ next to a SKU). Dealers: own locations only."""
    return stock_provenance(db, user, location_id, product_id)


@router.get("/transactions", response_model=list[TransactionOut])
def transactions(
    db: DB, user: Reader, location_id: int | None = None, product_id: int | None = None,
    reference_type: str | None = None, reference_id: int | None = None, txn_type: TxnType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100, offset: Annotated[int, Query(ge=0)] = 0,
    number: Annotated[str | None, Query(max_length=30)] = None,
):
    return ops.list_transactions(db, user, location_id=location_id, product_id=product_id,
                                 reference_type=reference_type, reference_id=reference_id, txn_type=txn_type,
                                 limit=limit, offset=offset, number=number)


@router.get("/transactions/{txn_id}", response_model=TransactionOut)
def transaction(txn_id: int, db: DB, user: Reader):
    _staff_only(user)
    txn = db.get(InventoryTransaction, txn_id)
    if txn is None:
        raise NotFoundError("Transaction not found")
    return txn


@router.post("/opening-balances", response_model=TransactionOut, status_code=201)
def opening_balance(data: OpeningBalanceIn, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_ADJUST))]):
    txn = ops.post_opening_balance(db, user, data)
    db.commit()
    return txn


@router.post("/adjustments", response_model=TransactionOut, status_code=201)
def adjustment(data: AdjustmentIn, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_ADJUST))]):
    txn = ops.post_adjustment(db, user, data)
    db.commit()
    return txn


@router.post("/block", response_model=TransactionOut, status_code=201)
def block(data: StockStateChangeIn, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_BLOCK))]):
    txn = ops.change_block(db, user, data, block=True)
    db.commit()
    return txn


@router.post("/unblock", response_model=TransactionOut, status_code=201)
def unblock(data: StockStateChangeIn, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_BLOCK))]):
    txn = ops.change_block(db, user, data, block=False)
    db.commit()
    return txn


@router.post("/write-offs", response_model=TransactionOut, status_code=201)
def write_off(data: StockStateChangeIn, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_ADJUST))]):
    txn = ops.write_off_blocked(db, user, data)
    db.commit()
    return txn


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation(db: DB, user: Reader, location_id: int | None = None):
    _staff_only(user)
    diffs = reconcile(db, location_id)
    unbalanced = unbalanced_transactions(db) if location_id is None else []
    return ReconciliationOut(
        balanced=not diffs and not unbalanced,
        checked_at=datetime.now(UTC),
        differences=[ReconciliationRow(**d.__dict__) for d in diffs],
        unbalanced_transaction_ids=unbalanced,
    )
