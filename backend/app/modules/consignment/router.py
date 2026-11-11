from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.permissions import P
from app.modules.consignment import service
from app.modules.consignment.schemas import AllocationChangeOut, AllocationIn, AllocationOut, AllocationPosition
from app.modules.identity.deps import DB, require
from app.modules.identity.models import User

router = APIRouter(tags=["consignment"])


@router.get("/allocations", response_model=list[AllocationOut])
def list_allocations(
    db: DB, user: Annotated[User, Depends(require(P.INVENTORY_READ))],
    reseller_id: int | None = None, location_id: int | None = None,
):
    return service.list_allocations(db, user, reseller_id=reseller_id, location_id=location_id)


@router.get("/allocations/positions", response_model=list[AllocationPosition])
def allocation_positions(
    db: DB, user: Annotated[User, Depends(require(P.INVENTORY_READ))],
    reseller_id: int | None = None, location_id: int | None = None,
):
    return service.positions(db, user, reseller_id=reseller_id, location_id=location_id)


@router.put("/allocations", response_model=AllocationOut)
def set_allocation(data: AllocationIn, db: DB, user: Annotated[User, Depends(require(P.ALLOCATION_WRITE))]):
    alloc = service.set_allocation(db, user, data)
    db.commit()
    return alloc


@router.get("/allocations/{allocation_id}/history", response_model=list[AllocationChangeOut])
def allocation_history(allocation_id: int, db: DB, user: Annotated[User, Depends(require(P.INVENTORY_READ))]):
    return service.allocation_history(db, user, allocation_id)
