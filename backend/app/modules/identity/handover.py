"""Staff handover when someone leaves or shares their work (finding 32, D9).

Moves a staff member's dealers (sales rep), the deliveries and transfers they are carrying, and the approvals waiting
for them, to a colleague with the same role, in one step. Deactivating a user is refused while any of these are still
theirs ("Hand them over first").
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.permissions import ROLE_LABELS, Role
from app.modules.audit.service import record_audit
from app.modules.customers.models import Reseller
from app.modules.identity.models import User
from app.modules.notifications.service import notify_users, reseller_users
from app.modules.replenishment.models import OPEN_STATUSES, Delivery, DeliveryStatus, ReplenishmentRequest
from app.modules.stock_requests.models import PENDING_STATUSES, StockRequest
from app.modules.transfers.models import Transfer, TransferStatus

NOT_RECEIVED = (TransferStatus.APPROVED.value, TransferStatus.IN_TRANSIT.value)


@dataclass
class Responsibilities:
    dealers: list[Reseller] = field(default_factory=list)
    deliveries: list[Delivery] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    stock_requests: list[StockRequest] = field(default_factory=list)
    replenishments: list[ReplenishmentRequest] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.dealers or self.deliveries or self.transfers or self.stock_requests or self.replenishments)

    def summary(self) -> str:
        parts = [(self.dealers, "dealer", lambda r: r.business_name), (self.deliveries, "delivery", lambda d: d.number),
                 (self.transfers, "transfer", lambda t: t.number),
                 (self.stock_requests, "approval", lambda s: s.number),
                 (self.replenishments, "replenishment approval", lambda r: r.number)]
        return "; ".join(f"{len(xs)} {name}{'' if len(xs) == 1 else 's'} ({', '.join(label(x) for x in xs)})"
                         for xs, name, label in parts if xs)


def responsibilities(db: Session, user: User, reseller_ids: set[int] | None = None) -> Responsibilities:
    """What is still this user's: their dealers, what they carry, and approvals waiting for them (optionally only for
    some dealers)."""
    def only(stmt, column):
        return stmt.where(column.in_(reseller_ids)) if reseller_ids is not None else stmt

    r = Responsibilities()
    r.dealers = list(db.execute(only(select(Reseller).where(Reseller.sales_rep_user_id == user.id), Reseller.id)
                                .order_by(Reseller.business_name)).scalars())
    r.deliveries = list(db.execute(only(select(Delivery).where(
        Delivery.carried_by_user_id == user.id, Delivery.status == DeliveryStatus.IN_TRANSIT), Delivery.reseller_id)
        .order_by(Delivery.id)).scalars())
    carried = (Transfer.carried_by_user_id == user.id) & Transfer.status.in_(NOT_RECEIVED)
    # Older transfers (nothing arranged) that this Sales Rep collected: only they could confirm them.
    collected = (Transfer.carried_by_user_id.is_(None) & (Transfer.collected_by_user_id == user.id)
                 & (Transfer.status == TransferStatus.IN_TRANSIT)) if user.role == Role.SALES_REP else None
    r.transfers = list(db.execute(only(select(Transfer).where(carried if collected is None else carried | collected),
                                       Transfer.destination_reseller_id).order_by(Transfer.id)).scalars())
    r.stock_requests = list(db.execute(only(select(StockRequest).where(
        StockRequest.escalated_to_user_id == user.id, StockRequest.status.in_([s.value for s in PENDING_STATUSES])),
        StockRequest.reseller_id).order_by(StockRequest.id)).scalars())
    r.replenishments = list(db.execute(only(select(ReplenishmentRequest).where(
        ReplenishmentRequest.escalated_to_user_id == user.id,
        ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES])), ReplenishmentRequest.reseller_id)
        .order_by(ReplenishmentRequest.id)).scalars())
    return r


def ensure_nothing_left(db: Session, user: User) -> None:
    """Deactivation guard (D9)."""
    left = responsibilities(db, user)
    if not left.empty():
        raise BusinessRuleError(f"{user.full_name} still has {left.summary()}. Hand them over first.")


def handover(db: Session, actor: User, from_user_id: int, *, to_user_id: int, reseller_ids: list[int] | None = None,
             deactivate: bool = False, reason: str) -> Responsibilities:
    """Move dealers, carried deliveries and transfers, and waiting approvals to a colleague with the same role.
    reseller_ids None = everything; a list = only those dealers (sharing the work). Services never commit."""
    leaver, taker = db.get(User, from_user_id), db.get(User, to_user_id)
    if leaver is None or taker is None or leaver.is_reseller_user or taker.is_reseller_user:
        raise NotFoundError("User not found")
    if leaver.id == taker.id:
        raise BusinessRuleError("Choose a different person to hand over to")
    if leaver.role != taker.role:
        raise BusinessRuleError(f"Hand over to someone with the same role ({ROLE_LABELS[Role(leaver.role)]})")
    if not taker.is_active:
        raise BusinessRuleError(f"{taker.full_name} is not active")
    reason = reason.strip()
    if len(reason) < 3:
        raise BusinessRuleError("Give a short reason for the handover")
    chosen = None
    if reseller_ids is not None:
        chosen = set(reseller_ids)
        if not chosen:
            raise BusinessRuleError("Choose at least one dealer to share")
        theirs = {r.id for r in responsibilities(db, leaver).dealers}
        if chosen - theirs:
            raise BusinessRuleError(f"{leaver.full_name} does not look after all the dealers chosen")
    if deactivate and leaver.id == actor.id:
        raise BusinessRuleError("You cannot deactivate yourself")
    if deactivate and chosen is not None:
        raise BusinessRuleError("Deactivate only when handing over everything")

    moved = responsibilities(db, leaver, chosen)
    for r in moved.dealers:
        r.sales_rep_user_id = taker.id
    for d in moved.deliveries:
        d.carried_by_user_id = taker.id
    for t in moved.transfers:
        t.carried_by_user_id = taker.id
        if t.shipping_method is None:
            t.shipping_method = "SALES_REP"
    for x in (*moved.stock_requests, *moved.replenishments):
        x.escalated_to_user_id = taker.id
    if deactivate:
        leaver.is_active = False
    db.flush()
    record_audit(db, actor_id=actor.id, action="user.handover", entity_type="user", entity_id=leaver.id,
                 summary=f"Handed over from {leaver.full_name} to {taker.full_name}: "
                         f"{moved.summary() or 'nothing open'}" + ("; deactivated" if deactivate else "") + f" ({reason})",
                 details={"to_user_id": taker.id, "reason": reason, "deactivated": deactivate,
                          "dealers": [r.id for r in moved.dealers], "deliveries": [d.id for d in moved.deliveries],
                          "transfers": [t.id for t in moved.transfers],
                          "stock_requests": [s.id for s in moved.stock_requests],
                          "replenishment_requests": [r.id for r in moved.replenishments]})
    if moved.dealers:
        names = ", ".join(r.business_name for r in moved.dealers)
        notify_users(db, [taker.id], f"You now look after {len(moved.dealers)} dealer(s): {names}",
                     f"Handed over by {actor.full_name} from {leaver.full_name}.", link="/resellers", exclude=actor.id)
        if taker.role == Role.SALES_REP:
            for r in moved.dealers:
                company = get_settings().company_name
                notify_users(db, reseller_users(db, r.id), f"Your {company} sales rep is now {taker.full_name}",
                             f"{taker.full_name} · {taker.email}" + (f" · {taker.phone}" if taker.phone else ""),
                             link="/", entity_type="reseller", entity_id=r.id)
    other = len(moved.deliveries) + len(moved.transfers) + len(moved.stock_requests) + len(moved.replenishments)
    if other:
        notify_users(db, [taker.id], f"{other} hand-over(s) and approval(s) are now yours",
                     moved.summary(), link="/", exclude=actor.id)
    return moved
