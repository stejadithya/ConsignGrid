"""Batch lookups used to enrich API responses with human-readable names (avoids N+1 queries)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session


def by_id(db: Session, model, ids: Iterable[int | None]) -> dict:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {o.id: o for o in db.execute(select(model).where(model.id.in_(wanted))).scalars()}


class Names:
    """Collects ids, then resolves products / locations / resellers / users in four queries."""

    def __init__(self, db: Session):
        self.db = db
        self._ids: dict[str, set[int]] = {"product": set(), "location": set(), "reseller": set(), "user": set()}
        self.products: dict = {}
        self.locations: dict = {}
        self.resellers: dict = {}
        self.users: dict = {}

    def add(self, kind: str, *ids: int | None) -> "Names":
        self._ids[kind].update(i for i in ids if i is not None)
        return self

    def resolve(self) -> "Names":
        from app.modules.catalogue.models import Product
        from app.modules.customers.models import Location, Reseller
        from app.modules.identity.models import User

        self.products = by_id(self.db, Product, self._ids["product"])
        self.locations = by_id(self.db, Location, self._ids["location"])
        self.resellers = by_id(self.db, Reseller, self._ids["reseller"])
        self.users = by_id(self.db, User, self._ids["user"])
        return self

    def sku(self, pid):
        p = self.products.get(pid)
        return p.sku if p else None

    def product_name(self, pid):
        p = self.products.get(pid)
        return p.display_name if p else None

    def loc_code(self, lid):
        loc = self.locations.get(lid)
        return loc.code if loc else None

    def loc_name(self, lid):
        loc = self.locations.get(lid)
        return loc.name if loc else None

    def reseller_name(self, rid):
        r = self.resellers.get(rid)
        return r.business_name if r else None

    def user_name(self, uid):
        u = self.users.get(uid)
        return u.full_name if u else None
