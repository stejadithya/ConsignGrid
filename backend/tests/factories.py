"""Test data builders. Creates realistic entities directly through the ORM and API helpers."""

from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.core.security import create_access_token, hash_password
from app.modules.catalogue.models import Product, TaxRate
from app.modules.consignment.models import ConsignmentAllocation
from app.modules.customers.models import (
    ConsignmentAgreement,
    Location,
    LocationType,
    Reseller,
    ResellerStatus,
    TransferConsent,
)
from app.modules.identity.models import User
from app.modules.inventory.models import StockBalance, TxnType
from app.modules.inventory.service import Ledger, Ref, system_location

_PW_HASH = hash_password("correct-horse-battery")


class Api:
    """Thin HTTP helper bound to a user; raises on unexpected status codes."""

    def __init__(self, client, user: User):
        self.client = client
        self.user = user
        self.headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    def _call(self, method: str, url: str, expected: int | tuple[int, ...] | None, **kw):
        resp = self.client.request(method, f"/api{url}", headers=self.headers, **kw)
        if expected is not None:
            exp = (expected,) if isinstance(expected, int) else expected
            assert resp.status_code in exp, f"{method} {url} → {resp.status_code}: {resp.text}"
        return resp

    def get(self, url, expected=200, **kw):
        return self._call("GET", url, expected, **kw)

    def post(self, url, json=None, expected=(200, 201), **kw):
        return self._call("POST", url, expected, json=json, **kw)

    def put(self, url, json=None, expected=200, **kw):
        return self._call("PUT", url, expected, json=json, **kw)

    def patch(self, url, json=None, expected=200, **kw):
        return self._call("PATCH", url, expected, json=json, **kw)


def make_user(db: Session, role: Role, email: str, reseller_id: int | None = None, name: str | None = None) -> User:
    u = User(email=email, full_name=name or email.split("@")[0].title(), password_hash=_PW_HASH, role=role,
             reseller_id=reseller_id, is_active=True)
    db.add(u)
    db.flush()
    return u


def make_product(db: Session, sku: str, *, brand="Michelin", pattern="Primacy 4", width=205, aspect=55, rim=16,
                 load="91", speed="V", list_price="180.00", cost_price="120.00") -> Product:
    p = Product(sku=sku, brand=brand, pattern=pattern, width=width, aspect_ratio=aspect,
                rim_diameter=Decimal(rim), load_index=load, speed_rating=speed,
                list_price=Decimal(list_price), cost_price=Decimal(cost_price), is_active=True)
    db.add(p)
    db.flush()
    return p


def make_reseller(db: Session, ref: str, name: str, *, consent=TransferConsent.PRE_AUTHORISED,
                  sales_rep: User | None = None) -> tuple[Reseller, Location]:
    r = Reseller(account_ref=ref, business_name=name, status=ResellerStatus.ACTIVE, payment_terms_days=30,
                 billing_address=f"1 {name} Street", sales_rep_user_id=sales_rep.id if sales_rep else None)
    db.add(r)
    db.flush()
    db.add(ConsignmentAgreement(reseller_id=r.id, reference=f"AGR-{ref}", transfer_consent=consent,
                                auto_replenish_default=True))
    loc = Location(code=f"{ref}-MAIN", name=f"{name} — Main", type=LocationType.CONSIGNMENT, reseller_id=r.id,
                   city="Springfield", is_active=True)
    db.add(loc)
    db.flush()
    return r, loc


def set_stock(db: Session, location: Location, product: Product, qty: int, actor: User | None = None) -> None:
    """Post an opening balance through the ledger (never write balances directly)."""
    if qty <= 0:
        return
    ledger = Ledger(db, TxnType.OPENING_BALANCE, actor_id=actor.id if actor else None,
                    ref=Ref("test", None, "TEST"))
    ledger.move(product.id, system_location(db, LocationType.OPENING), location, qty)
    db.flush()


def set_target(db: Session, location: Location, product: Product, target: int, auto: bool = True):
    a = ConsignmentAllocation(location_id=location.id, product_id=product.id, target_qty=target,
                              auto_replenish=auto, is_active=True)
    db.add(a)
    db.flush()
    return a


def balance(db: Session, location: Location, product: Product) -> StockBalance:
    db.expire_all()
    b = db.get(StockBalance, (location.id, product.id))
    return b or StockBalance(location_id=location.id, product_id=product.id, on_hand=0, reserved=0, blocked=0)


@dataclass
class World:
    db: Session
    client: object
    warehouse: Location
    tax: TaxRate
    admin: User
    manager: User
    warehouse_op: User
    rep: User
    finance: User
    reseller_a: Reseller
    reseller_b: Reseller
    reseller_c: Reseller
    loc_a: Location
    loc_b: Location
    loc_c: Location
    user_a: User
    user_b: User
    p1: Product
    p2: Product
    p3: Product
    _apis: dict = field(default_factory=dict)

    def api(self, user: User) -> Api:
        if user.id not in self._apis:
            self._apis[user.id] = Api(self.client, user)
        return self._apis[user.id]

    def bal(self, location: Location, product: Product) -> StockBalance:
        return balance(self.db, location, product)


@pytest.fixture
def world(db, client) -> World:
    tax = TaxRate(code="STD", name="Standard rate (test)", rate=Decimal("0.1000"), is_default=True, is_active=True)
    db.add(tax)
    admin = make_user(db, Role.RELATIONSHIP_MANAGER, "admin@example.com", name="Ada Admin")   # user administration
    manager = make_user(db, Role.RELATIONSHIP_MANAGER, "manager@example.com", name="Morgan Manager")
    wh_op = make_user(db, Role.WAREHOUSE_MANAGER, "warehouse@example.com", name="Wes Warehouse")
    rep = make_user(db, Role.SALES_REP, "rep@example.com", name="Riley Rep")
    finance = make_user(db, Role.RELATIONSHIP_MANAGER, "finance@example.com", name="Frankie Finance")  # invoicing

    warehouse = Location(code="WH-MAIN", name="Central Warehouse", type=LocationType.WAREHOUSE,
                         is_default_warehouse=True, is_active=True)
    db.add(warehouse)
    ra, la = make_reseller(db, "RA", "Alpha Tyres", sales_rep=rep)
    rb, lb = make_reseller(db, "RB", "Bravo Auto", sales_rep=rep)
    rc, lc = make_reseller(db, "RC", "Charlie Wheels", consent=TransferConsent.PER_TRANSFER)
    user_a = make_user(db, Role.RESELLER, "alpha@example.com", reseller_id=ra.id)
    user_b = make_user(db, Role.RESELLER, "bravo@example.com", reseller_id=rb.id)
    p1 = make_product(db, "TYR-001")
    p2 = make_product(db, "TYR-002", brand="Bridgestone", pattern="Turanza T005", width=225, aspect=45, rim=17,
                      load="94", speed="W", list_price="210.00", cost_price="140.00")
    p3 = make_product(db, "TYR-003", brand="Continental", pattern="PremiumContact 7", width=205, aspect=55,
                      rim=16, load="91", speed="V", list_price="195.00", cost_price="130.00")
    db.commit()
    return World(db=db, client=client, warehouse=warehouse, tax=tax, admin=admin, manager=manager,
                 warehouse_op=wh_op, rep=rep, finance=finance, reseller_a=ra, reseller_b=rb, reseller_c=rc,
                 loc_a=la, loc_b=lb, loc_c=lc, user_a=user_a, user_b=user_b, p1=p1, p2=p2, p3=p3)


@pytest.fixture
def ledger_balanced(world):
    """Release 1.11 tests end with the stock ledger reconciled (final gate P16.4); applied with pytestmark."""
    yield
    assert world.api(world.warehouse_op).get("/inventory/reconciliation").json()["balanced"] is True


# What a Sales Rep records when handing stock to a dealer (required for Sales Rep confirmations).
HANDOVER = {"received_by_name": "Shop owner", "notes": "Handed over at the counter"}
# Approval details every stock request approval now needs (1.11, finding 17).
APPROVAL = {"method": "PHONE", "contact": "Dealer owner", "comments": "Agreed on the phone"}
