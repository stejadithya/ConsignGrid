"""Journey-specific stock check (release 1.11, finding 7): for the tyres on a request, is there stock in the warehouse,
how many does this dealer already hold, and how many could other dealers spare? Read-only, staff only.

A fixed number of queries whatever the number of tyres (no query per product)."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.modules.customers.models import Location, LocationType, Reseller, ResellerStatus
from app.modules.inventory.models import StockBalance
from app.modules.inventory.service import default_warehouse

_AVAILABLE = StockBalance.on_hand - StockBalance.reserved - StockBalance.blocked


@dataclass
class ProductAvailability:
    product_id: int
    warehouse_available: int = 0
    warehouse_on_hand: int = 0
    at_this_location: dict | None = None            # {on_hand, available} when a dealer location is given
    dealer_total_on_hand: int | None = None          # all of that dealer's shops
    other_dealers: dict = field(default_factory=lambda: {"available": 0, "locations": 0})


def check(db: Session, product_ids: list[int], dealer_location_id: int | None = None) -> list[ProductAvailability]:
    ids = list(dict.fromkeys(product_ids))
    out = {pid: ProductAvailability(product_id=pid) for pid in ids}
    if not ids:
        return []
    dealer_id = None
    if dealer_location_id is not None:
        loc = db.get(Location, dealer_location_id)
        if loc is None or loc.type != LocationType.CONSIGNMENT:
            raise NotFoundError("Dealer location not found")
        dealer_id = loc.reseller_id
        for a in out.values():
            a.at_this_location, a.dealer_total_on_hand = {"on_hand": 0, "available": 0}, 0

    # 1. Main warehouse.
    wh = default_warehouse(db)
    for pid, on_hand, available in db.execute(
        select(StockBalance.product_id, StockBalance.on_hand, _AVAILABLE)
        .where(StockBalance.location_id == wh.id, StockBalance.product_id.in_(ids))
    ):
        out[pid].warehouse_on_hand, out[pid].warehouse_available = on_hand, available

    # 2. Every dealer shop holding these tyres, grouped per product and shop.
    rows = db.execute(
        select(StockBalance.product_id, StockBalance.location_id, Location.reseller_id, Reseller.status,
               StockBalance.on_hand, _AVAILABLE)
        .join(Location, Location.id == StockBalance.location_id)
        .join(Reseller, Reseller.id == Location.reseller_id)
        .where(Location.type == LocationType.CONSIGNMENT, StockBalance.product_id.in_(ids),
               StockBalance.on_hand > 0, Reseller.is_cash_account.is_(False))
    ).all()
    for pid, location_id, reseller_id, status, on_hand, available in rows:
        a = out[pid]
        if dealer_id is not None and reseller_id == dealer_id:
            a.dealer_total_on_hand += on_hand
            if location_id == dealer_location_id:
                a.at_this_location = {"on_hand": on_hand, "available": available}
        elif status == ResellerStatus.ACTIVE and available > 0:
            a.other_dealers["available"] += available
            a.other_dealers["locations"] += 1
    return [out[pid] for pid in ids]


def dealer_holdings(db: Session, location_id: int, product_ids: list[int]) -> dict[int, tuple[int, int]]:
    """{product_id: (on hand at this shop, on hand at all of this dealer's shops)} in one query (finding 20)."""
    loc = db.get(Location, location_id)
    ids = list(dict.fromkeys(product_ids))
    out = {pid: [0, 0] for pid in ids}
    if loc is None or loc.reseller_id is None or not ids:
        return {pid: (0, 0) for pid in ids}
    for pid, lid, on_hand in db.execute(
        select(StockBalance.product_id, StockBalance.location_id, StockBalance.on_hand)
        .join(Location, Location.id == StockBalance.location_id)
        .where(Location.reseller_id == loc.reseller_id, Location.type == LocationType.CONSIGNMENT,
               StockBalance.product_id.in_(ids))
    ):
        out[pid][1] += on_hand
        if lid == location_id:
            out[pid][0] += on_hand
    return {pid: (v[0], v[1]) for pid, v in out.items()}

