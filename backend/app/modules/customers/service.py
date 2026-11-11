import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.db import flush_or_conflict
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.industry import vocab
from app.core.permissions import Role
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product, TaxRate
from app.modules.customers import refs
from app.modules.customers.models import (
    ConsignmentAgreement,
    CustomerPrice,
    Location,
    LocationType,
    Reseller,
    ResellerStatus,
)
from app.modules.customers.schemas import (
    AgreementIn,
    CustomerPriceIn,
    DealerLoginOut,
    DealerShopIn,
    LocationIn,
    ResellerCreate,
    ResellerOut,
    ResellerStatusChange,
    ResellerSummary,
    ResellerUpdate,
    WarehouseIn,
)
from app.modules.identity.models import User
from app.modules.identity.schemas import UserCreate
from app.modules.identity.scoping import ensure_reseller_access, scoped_reseller_id
from app.modules.identity.service import create_user


def get_reseller(db: Session, user: User, reseller_id: int) -> Reseller:
    ensure_reseller_access(user, reseller_id, vocab.Partner)
    r = db.execute(
        select(Reseller)
        .where(Reseller.id == reseller_id)
        .options(selectinload(Reseller.locations), selectinload(Reseller.agreement))
    ).scalar_one_or_none()
    if r is None:
        raise NotFoundError(f"{vocab.Partner} not found")
    return r


def reseller_out(db: Session, r: Reseller) -> ResellerOut:
    out = ResellerOut.model_validate(r)
    if r.sales_rep_user_id:
        rep = db.get(User, r.sales_rep_user_id)
        out.sales_rep_name = rep.full_name if rep else None
    return out


def list_resellers(
    db: Session, user: User, *, q: str | None = None, status: ResellerStatus | None = None,
    sales_rep_user_id: int | None = None,
) -> list[ResellerSummary]:
    loc_count = (
        select(Location.reseller_id, func.count(Location.id).label("n"))
        .where(Location.reseller_id.is_not(None))
        .group_by(Location.reseller_id)
        .subquery()
    )
    stmt = (
        select(Reseller, User.full_name, func.coalesce(loc_count.c.n, 0))
        .outerjoin(User, User.id == Reseller.sales_rep_user_id)
        .outerjoin(loc_count, loc_count.c.reseller_id == Reseller.id)
        .where(Reseller.is_cash_account.is_(False))   # the walk-in cash sales account is not a reseller
    )
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Reseller.id == restricted)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Reseller.business_name.ilike(like), Reseller.account_ref.ilike(like),
                              Reseller.trading_name.ilike(like)))
    if status:
        stmt = stmt.where(Reseller.status == status)
    if sales_rep_user_id:
        stmt = stmt.where(Reseller.sales_rep_user_id == sales_rep_user_id)
    out = []
    for r, rep_name, n in db.execute(stmt.order_by(Reseller.business_name)):
        s = ResellerSummary.model_validate(r)
        s.sales_rep_name = rep_name
        s.location_count = n
        out.append(s)
    return out


def _validate_refs(db: Session, sales_rep_user_id: int | None, tax_rate_id: int | None) -> None:
    if sales_rep_user_id is not None:
        rep = db.get(User, sales_rep_user_id)
        if rep is None or rep.role != Role.SALES_REP or not rep.is_active:
            raise BusinessRuleError("Sales representative must be an active Sales Representative")
    if tax_rate_id is not None and db.get(TaxRate, tax_rate_id) is None:
        raise NotFoundError("Tax rate not found")


def create_reseller(db: Session, actor: User, data: ResellerCreate) -> tuple[Reseller, DealerLoginOut | None]:
    _validate_refs(db, data.sales_rep_user_id, data.tax_rate_id)
    login_email = str(data.email).lower() if data.create_login else None
    if login_email and db.execute(select(User.id).where(func.lower(User.email) == login_email)).first():
        raise ConflictError(f"A login with the email {login_email} already exists. Nothing was created.")
    fields = data.model_dump(exclude={"agreement", "locations", "create_login"})
    if data.account_ref:
        reseller = Reseller(**fields, status=ResellerStatus.ACTIVE)
        flush_or_conflict(db, reseller, f"{vocab.APartner} with this account reference already exists")
    else:
        reseller = _create_with_generated_ref(db, data, fields)
    if data.agreement:
        db.add(ConsignmentAgreement(reseller_id=reseller.id, **data.agreement.model_dump()))
    for loc in data.locations:
        _add_shop(db, reseller, loc)
    db.flush()
    record_audit(db, actor_id=actor.id, action="reseller.create", entity_type="reseller", entity_id=reseller.id,
                 reseller_id=reseller.id, summary=f"Created {vocab.partner} {reseller.account_ref} {reseller.business_name}")
    login = None
    if login_email:
        password = temporary_password()
        create_user(db, actor, UserCreate(email=login_email, full_name=data.contact_name, password=password,
                                          role=Role.RESELLER, reseller_id=reseller.id))
        login = DealerLoginOut(email=login_email, temporary_password=password)   # shown once; never logged
    db.refresh(reseller)
    return reseller, login


# Letters and digits that cannot be confused when read aloud or copied by hand (no 0/O, 1/l/I).
_UNAMBIGUOUS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def temporary_password(length: int = 12) -> str:
    return "".join(secrets.choice(_UNAMBIGUOUS) for _ in range(length))


def _create_with_generated_ref(db: Session, data: ResellerCreate, fields: dict) -> Reseller:
    city = data.locations[0].city if data.locations else None
    for attempt in (1, 2):   # one retry if a reference was taken in the meantime
        fields["account_ref"] = refs.next_account_ref(db, data.business_name, city)
        reseller = Reseller(**fields, status=ResellerStatus.ACTIVE)
        try:
            flush_or_conflict(db, reseller, f"{vocab.APartner} with this account reference already exists")
            return reseller
        except ConflictError:
            db.expunge(reseller)
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def update_reseller(db: Session, actor: User, reseller_id: int, data: ResellerUpdate) -> Reseller:
    reseller = get_reseller(db, actor, reseller_id)
    changes = data.model_dump(exclude_unset=True)
    _validate_refs(db, changes.get("sales_rep_user_id"), changes.get("tax_rate_id"))
    for k, v in changes.items():
        setattr(reseller, k, v)
    db.flush()
    record_audit(db, actor_id=actor.id, action="reseller.update", entity_type="reseller", entity_id=reseller.id,
                 reseller_id=reseller.id, summary=f"Updated {vocab.partner} {reseller.account_ref}",
                 details={k: str(v) for k, v in changes.items()})
    return reseller


def change_status(db: Session, actor: User, reseller_id: int, data: ResellerStatusChange) -> Reseller:
    reseller = get_reseller(db, actor, reseller_id)
    old = reseller.status
    reseller.status = data.status
    db.flush()
    record_audit(db, actor_id=actor.id, action="reseller.status", entity_type="reseller", entity_id=reseller.id,
                 reseller_id=reseller.id, summary=f"Status {old} → {data.status}: {data.reason}")
    return reseller


def save_agreement(db: Session, actor: User, reseller_id: int, data: AgreementIn) -> ConsignmentAgreement:
    reseller = get_reseller(db, actor, reseller_id)
    agreement = reseller.agreement
    if agreement is None:
        agreement = ConsignmentAgreement(reseller_id=reseller.id, **data.model_dump())
        db.add(agreement)
    else:
        for k, v in data.model_dump().items():
            setattr(agreement, k, v)
    db.flush()
    record_audit(db, actor_id=actor.id, action="agreement.save", entity_type="consignment_agreement",
                 entity_id=agreement.id, reseller_id=reseller.id,
                 summary=f"Saved consignment agreement {agreement.reference}",
                 details=data.model_dump(mode="json"))
    return agreement


def _add_location(db: Session, reseller_id: int | None, loc_type: LocationType, data: LocationIn) -> Location:
    fields = data.model_dump()
    loc = Location(type=loc_type, reseller_id=reseller_id, **fields)
    flush_or_conflict(db, loc, f"Location code {data.code} already exists")
    return loc


def _next_shop_code(db: Session, reseller: Reseller) -> str:
    """{ACCOUNT_REF}-NN: the next number after the highest existing one for this dealer."""
    prefix = f"{reseller.account_ref}-"
    taken = db.execute(select(Location.code).where(Location.code.like(f"{prefix}%"))).scalars()
    numbers = [int(c[len(prefix):]) for c in taken if c[len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:02d}"


def _add_shop(db: Session, reseller: Reseller, data: DealerShopIn) -> Location:
    if not data.code:
        data = data.model_copy(update={"code": _next_shop_code(db, reseller)})
    return _add_location(db, reseller.id, LocationType.CONSIGNMENT, data)


def add_reseller_location(db: Session, actor: User, reseller_id: int, data: DealerShopIn) -> Location:
    reseller = get_reseller(db, actor, reseller_id)
    loc = _add_shop(db, reseller, data)
    record_audit(db, actor_id=actor.id, action="location.create", entity_type="location", entity_id=loc.id,
                 reseller_id=reseller.id, summary=f"Added consignment location {loc.code}")
    return loc


def update_location(db: Session, actor: User, location_id: int, data: LocationIn) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.type not in (LocationType.CONSIGNMENT, LocationType.WAREHOUSE):
        raise NotFoundError("Location not found")
    fields = data.model_dump(exclude={"is_default_warehouse"})
    for k, v in fields.items():
        setattr(loc, k, v)
    if isinstance(data, WarehouseIn) and loc.type == LocationType.WAREHOUSE:
        _set_default_warehouse(db, loc, data.is_default_warehouse)
    flush_or_conflict(db, None, f"Location code {data.code} already exists")
    record_audit(db, actor_id=actor.id, action="location.update", entity_type="location", entity_id=loc.id,
                 reseller_id=loc.reseller_id, summary=f"Updated location {loc.code}")
    return loc


def _set_default_warehouse(db: Session, loc: Location, is_default: bool) -> None:
    if is_default:
        db.execute(update(Location).where(Location.id != loc.id).values(is_default_warehouse=False))
    loc.is_default_warehouse = is_default


def create_warehouse(db: Session, actor: User, data: WarehouseIn) -> Location:
    loc = Location(type=LocationType.WAREHOUSE, **data.model_dump(exclude={"is_default_warehouse"}))
    flush_or_conflict(db, loc, f"Location code {data.code} already exists")
    has_default = db.execute(
        select(func.count()).select_from(Location).where(Location.is_default_warehouse.is_(True))
    ).scalar_one()
    _set_default_warehouse(db, loc, data.is_default_warehouse or has_default == 0)
    db.flush()
    record_audit(db, actor_id=actor.id, action="location.create", entity_type="location", entity_id=loc.id,
                 summary=f"Created warehouse {loc.code}")
    return loc


def list_locations(db: Session, user: User, *, types: list[LocationType] | None = None,
                   reseller_id: int | None = None, active: bool | None = None) -> list[Location]:
    stmt = select(Location)
    restricted = scoped_reseller_id(user)
    if restricted is not None:
        stmt = stmt.where(Location.reseller_id == restricted)
    if types:
        stmt = stmt.where(Location.type.in_([t.value for t in types]))
    if reseller_id is not None:
        stmt = stmt.where(Location.reseller_id == reseller_id)
    if active is not None:
        stmt = stmt.where(Location.is_active.is_(active))
    return list(db.execute(stmt.options(selectinload(Location.reseller))
                           .order_by(Location.type, Location.name)).scalars())


def get_location_scoped(db: Session, user: User, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if loc is None:
        raise NotFoundError("Location not found")
    restricted = scoped_reseller_id(user)
    if restricted is not None and loc.reseller_id != restricted:
        raise NotFoundError("Location not found")
    return loc


def get_consignment_location(db: Session, user: User, location_id: int) -> Location:
    loc = get_location_scoped(db, user, location_id)
    if loc.type != LocationType.CONSIGNMENT:
        raise BusinessRuleError(f"{loc.code} is not {vocab.aPartner} consignment location")
    return loc


# ---------------------------------------------------------------------------
# Customer-specific pricing
# ---------------------------------------------------------------------------


def list_prices(db: Session, user: User, reseller_id: int) -> list[tuple[CustomerPrice, str]]:
    ensure_reseller_access(user, reseller_id, vocab.Partner)
    rows = db.execute(
        select(CustomerPrice, Product.sku)
        .join(Product, Product.id == CustomerPrice.product_id)
        .where(CustomerPrice.reseller_id == reseller_id)
        .order_by(Product.sku, CustomerPrice.valid_from.desc())
    )
    return list(rows.tuples())


def add_price(db: Session, actor: User, reseller_id: int, data: CustomerPriceIn) -> CustomerPrice:
    get_reseller(db, actor, reseller_id)
    if db.get(Product, data.product_id) is None:
        raise NotFoundError("Product not found")
    if data.valid_to and data.valid_to < data.valid_from:
        raise BusinessRuleError("valid_to must be on or after valid_from")
    price = CustomerPrice(reseller_id=reseller_id, created_by_user_id=actor.id, **data.model_dump())
    flush_or_conflict(db, price, "A price for this product already starts on that date")
    record_audit(db, actor_id=actor.id, action="price.create", entity_type="customer_price", entity_id=price.id,
                 reseller_id=reseller_id, summary=f"Customer price {price.unit_price} from {price.valid_from}",
                 details=data.model_dump(mode="json"))
    return price


def effective_price(db: Session, reseller_id: int, product: Product, on: date) -> tuple[Decimal | None, str]:
    """Agreed price on a date: effective customer price, else product list price (A-006)."""
    price = db.execute(
        select(CustomerPrice.unit_price)
        .where(
            CustomerPrice.reseller_id == reseller_id, CustomerPrice.product_id == product.id,
            CustomerPrice.valid_from <= on,
            or_(CustomerPrice.valid_to.is_(None), CustomerPrice.valid_to >= on),
        )
        .order_by(CustomerPrice.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if price is not None:
        return price, "CUSTOMER_PRICE"
    return product.list_price, "LIST_PRICE"
