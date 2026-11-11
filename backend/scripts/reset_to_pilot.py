"""Reset the database to a CLEAN PILOT STATE. Explicit, one-time, destructive operation.

    python -m scripts.reset_to_pilot --dry-run                 # show what is there, change nothing
    python -m scripts.reset_to_pilot --confirm RESET-PILOT     # wipe and recreate the pilot baseline

What it does:
  1. Deletes ALL business data (products, stock, ledger, resellers, sales, stocktakes, replenishment,
     transfers, purchasing, invoices, audit history, feedback) and ALL users.
  2. Recreates required system configuration only: the ledger's virtual system locations, one
     warehouse location and one default tax rate (both configurable through environment variables).
  3. Creates only the pilot business accounts (Relationship Manager, Warehouse Manager, Sales
     Representative and, when the real pilot reseller is configured, the Reseller user).

It never runs automatically: deployments and migrations do not call it. With APP_ENV=production it also
requires --allow-production AND PILOT_RESET_ALLOW_PRODUCTION=yes.

Configuration (environment variables):
  PILOT_ADMIN_EMAIL, PILOT_ADMIN_NAME, PILOT_ADMIN_PASSWORD optional: the Administrator (super user)
  PILOT_RM_EMAIL, PILOT_WM_EMAIL, PILOT_SR_EMAIL           required: staff login emails
  PILOT_RM_NAME, PILOT_WM_NAME, PILOT_SR_NAME               optional display names
  PILOT_RM_PASSWORD, PILOT_WM_PASSWORD, PILOT_SR_PASSWORD   optional; generated and printed once if absent
  PILOT_RESELLER_EMAIL, PILOT_RESELLER_NAME, PILOT_RESELLER_PASSWORD
  PILOT_RESELLER_BUSINESS_NAME, PILOT_RESELLER_ACCOUNT_REF  the real pilot reseller organisation; if either
  PILOT_RESELLER_LOCATION_CODE, PILOT_RESELLER_LOCATION_NAME  is missing, the reseller user is not created
  PILOT_WAREHOUSE_CODE (WH-MAIN), PILOT_WAREHOUSE_NAME (Main Warehouse)
  PILOT_TAX_CODE (GST), PILOT_TAX_NAME (GST 15%), PILOT_TAX_RATE (0.15)

All accounts must change their password at first sign-in. Passwords are never written to the repository.
(Automated end-to-end tests on a disposable local database may set PILOT_FORCE_PASSWORD_CHANGE=false; this is
refused when APP_ENV is production or staging.)
"""

import argparse
import os
import secrets
import sys
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, text

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, get_engine, session_factory
from app.core.permissions import ROLE_LABELS, Role
from app.core.security import hash_password
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import TaxRate
from app.modules.customers.models import SYSTEM_LOCATIONS, Location, LocationType, Reseller, ResellerStatus
from app.modules.identity.models import User

CONFIRM_PHRASE = "RESET-PILOT"

# Business entities reported before/after the reset (label, table).
ENTITY_TABLES = [
    ("Users", "users"), ("Products", "products"), ("Tax rates", "tax_rates"), ("Dealers", "resellers"),
    ("Locations (all)", "locations"), ("Consignment targets", "consignment_allocations"),
    ("Customer prices", "customer_prices"), ("Stock balance rows", "stock_balances"),
    ("Ledger transactions", "inventory_transactions"), ("Stock reservations", "stock_reservations"),
    ("Purchase orders", "purchase_orders"), ("Goods receipts", "goods_receipts"), ("Sales", "consignment_sales"),
    ("Stocktakes", "stocktakes"), ("Replenishment requests", "replenishment_requests"),
    ("Deliveries", "deliveries"), ("Transfers", "transfers"), ("Invoices", "invoices"),
    ("Audit events", "audit_events"), ("Pilot feedback", "pilot_feedback"),
]


@dataclass
class Account:
    role: Role
    email: str
    name: str
    password: str
    generated: bool


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def _account(prefix: str, role: Role, required: bool = True) -> Account | None:
    email = _env(f"PILOT_{prefix}_EMAIL")
    if not email:
        if required:
            sys.exit(f"Missing PILOT_{prefix}_EMAIL (login email for the {ROLE_LABELS[role]}).")
        return None
    password = _env(f"PILOT_{prefix}_PASSWORD")
    if not password and os.environ.get("GITHUB_ACTIONS") == "true":
        # CI logs are kept and visible to collaborators: never print generated passwords there.
        sys.exit(f"Add the PILOT_{prefix}_PASSWORD repository secret (temporary password, at least 10 characters).")
    if password and len(password) < 10:
        sys.exit(f"PILOT_{prefix}_PASSWORD must be at least 10 characters.")
    return Account(role=role, email=email.lower(), name=_env(f"PILOT_{prefix}_NAME", ROLE_LABELS[role]),
                   password=password or secrets.token_urlsafe(12), generated=not password)


def counts(conn) -> dict[str, int]:
    out = {}
    for label, table in ENTITY_TABLES:
        exists = conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}).scalar()
        out[label] = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar() if exists else 0
    return out


def print_counts(title: str, data: dict[str, int]) -> None:
    print(f"\n{title}")
    for label, n in data.items():
        print(f"  {label:<26} {n}")


def guard(args: argparse.Namespace) -> None:
    if args.dry_run:
        return
    if args.confirm != CONFIRM_PHRASE:
        sys.exit(f"Refusing to reset: pass --confirm {CONFIRM_PHRASE} to delete all operational data.")
    if get_settings().app_env == "production" and not (
        args.allow_production and os.environ.get("PILOT_RESET_ALLOW_PRODUCTION") == "yes"
    ):
        sys.exit("Refusing to reset a production database: requires --allow-production and "
                 "PILOT_RESET_ALLOW_PRODUCTION=yes.")


def reset(args: argparse.Namespace) -> dict[str, int]:
    guard(args)
    engine = get_engine()
    with engine.connect() as conn:
        before = counts(conn)
    print_counts("Current contents:", before)
    if args.dry_run:
        print("\nDry run: nothing changed.")
        return before

    force_change = os.environ.get("PILOT_FORCE_PASSWORD_CHANGE", "true").lower() != "false"
    if not force_change and get_settings().app_env in ("production", "staging"):
        sys.exit("PILOT_FORCE_PASSWORD_CHANGE=false is only allowed for local test databases.")
    staff = [_account("RM", Role.RELATIONSHIP_MANAGER), _account("WM", Role.WAREHOUSE_MANAGER),
             _account("SR", Role.SALES_REP)]
    admin = _account("ADMIN", Role.ADMINISTRATOR, required=False)
    if admin:
        staff.insert(0, admin)
    reseller_account = _account("RESELLER", Role.RESELLER, required=False)
    business_name, account_ref = _env("PILOT_RESELLER_BUSINESS_NAME"), _env("PILOT_RESELLER_ACCOUNT_REF")

    print("\nWARNING: deleting ALL operational data and users …")
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        for loc_type, code, name in SYSTEM_LOCATIONS:
            conn.execute(text("INSERT INTO locations (code, name, type, is_default_warehouse, is_active) "
                              "VALUES (:c, :n, :t, false, true)"), {"c": code, "n": name, "t": loc_type.value})

    db = session_factory()()
    try:
        users: dict[Role, User] = {}
        for acc in staff:
            u = User(email=acc.email, full_name=acc.name, password_hash=hash_password(acc.password), role=acc.role,
                     is_active=True, must_change_password=force_change)
            db.add(u)
            users[acc.role] = u
        db.flush()
        rm = users[Role.RELATIONSHIP_MANAGER]

        db.add(Location(code=_env("PILOT_WAREHOUSE_CODE", "WH-MAIN").upper(),
                        name=_env("PILOT_WAREHOUSE_NAME", "Main Warehouse"), type=LocationType.WAREHOUSE,
                        is_default_warehouse=True, is_active=True))
        db.add(TaxRate(code=_env("PILOT_TAX_CODE", "GST"), name=_env("PILOT_TAX_NAME", "GST 15%"),
                       rate=Decimal(_env("PILOT_TAX_RATE", "0.15")), is_default=True, is_active=True))
        db.flush()

        created = list(staff)
        if reseller_account and business_name and account_ref:
            loc_code = _env("PILOT_RESELLER_LOCATION_CODE", f"{account_ref}-MAIN")
            # Saved directly with the details the secrets provide (no invented phone or address): the dealer's page
            # then shows "Missing details" until they are filled in (finding 9).
            reseller = Reseller(account_ref=account_ref.strip().upper(), business_name=business_name,
                                contact_name=reseller_account.name, email=reseller_account.email,
                                sales_rep_user_id=users[Role.SALES_REP].id, status=ResellerStatus.ACTIVE)
            db.add(reseller)
            db.flush()
            db.add(Location(code=loc_code.strip().upper(), name=_env("PILOT_RESELLER_LOCATION_NAME", business_name),
                            type=LocationType.CONSIGNMENT, reseller_id=reseller.id))
            db.flush()
            record_audit(db, actor_id=rm.id, action="reseller.create", entity_type="reseller", entity_id=reseller.id,
                         reseller_id=reseller.id, summary=f"Created dealer {reseller.account_ref} {reseller.business_name}")
            db.add(User(email=reseller_account.email, full_name=reseller_account.name,
                        password_hash=hash_password(reseller_account.password), role=Role.RESELLER,
                        reseller_id=reseller.id, is_active=True, must_change_password=force_change))
            created.append(reseller_account)
        elif reseller_account:
            print("\nNOTE: PILOT_RESELLER_BUSINESS_NAME / PILOT_RESELLER_ACCOUNT_REF not set — the dealer "
                  "user was NOT created. Create the dealer account in the app, then add its user under "
                  "Administration → Users.")

        record_audit(db, actor_id=None, action="system.pilot_reset", entity_type="system", entity_id=None,
                     summary="Database reset to clean pilot state")
        db.commit()
        n_users = db.execute(select(func.count()).select_from(User)).scalar_one()
    finally:
        db.close()

    with engine.connect() as conn:
        after = counts(conn)
    print_counts("After reset:", after)
    note = "every account must change its password at first sign-in" if force_change else "TEST MODE: no forced password change"
    print(f"\nPilot accounts created ({n_users}) — {note}:")
    for acc in created:
        shown = acc.password if acc.generated else "(from environment variable)"
        print(f"  {ROLE_LABELS[acc.role]:<22} {acc.email:<36} temporary password: {shown}")
    if any(a.generated for a in created):
        print("\nGenerated passwords are shown only once. Share them privately; they are not stored anywhere else.")
    return after


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the database to a clean pilot state (destructive).")
    parser.add_argument("--confirm", help=f"must be exactly {CONFIRM_PHRASE}")
    parser.add_argument("--dry-run", action="store_true", help="show current counts only")
    parser.add_argument("--allow-production", action="store_true",
                        help="also requires PILOT_RESET_ALLOW_PRODUCTION=yes")
    reset(parser.parse_args())


if __name__ == "__main__":
    main()
