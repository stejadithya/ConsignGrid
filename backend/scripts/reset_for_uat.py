"""Clean the database for UAT. Explicit, one-time, destructive operation.

    python -m scripts.reset_for_uat --dry-run                  # show what would be kept / deleted, change nothing
    python -m scripts.reset_for_uat --confirm CLEAN-FOR-UAT    # clean up and put 10 of every active SKU in stock

KEEPS: user logins, dealers (accounts, locations, agreements and agreement copies), dealer-specific prices,
products (SKUs), tax rates, app settings (e.g. photo archiving).
DELETES everything else: all stock and stock movements, stock requests, replenishment requests and backorders,
deliveries, transfers, sales (including cash sales), invoices, stocktakes, purchase orders and goods receipts,
dealer agreed stock levels (targets and their history), notifications, change history (audit) and feedback.
Document numbers (SRQ-, DEL-, SAL-, …) restart from 000001.
THEN: posts an opening balance of 10 units of every ACTIVE product in the default warehouse.

It never runs automatically: deployments and migrations do not call it. With APP_ENV=production it also
requires --allow-production AND UAT_RESET_ALLOW_PRODUCTION=yes.
"""

import argparse
import os
import sys

from sqlalchemy import select, text

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, get_engine, session_factory
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.customers.models import LocationType
from app.modules.inventory.models import TxnType
from app.modules.inventory.service import Ledger, Ref, default_warehouse, system_location

CONFIRM_PHRASE = "CLEAN-FOR-UAT"
UNITS_PER_SKU = 10

KEEP = {"users", "resellers", "locations", "consignment_agreements", "consignment_agreement_files", "customer_prices",
        "products", "tax_rates", "app_settings"}


def plan() -> tuple[list[str], list[str]]:
    """(tables kept, tables emptied). Refuses if a kept table points at one that would be emptied."""
    tables = {t.name: t for t in Base.metadata.tables.values()}
    missing = KEEP - set(tables)
    if missing:
        sys.exit(f"Unknown tables in keep list: {sorted(missing)}")
    wipe = sorted(set(tables) - KEEP)
    for name in sorted(KEEP):
        for fk in tables[name].foreign_keys:
            if fk.column.table.name in wipe:
                sys.exit(f"Refusing: kept table {name} references {fk.column.table.name}, which would be emptied.")
    return sorted(KEEP), wipe


def counts(conn, tables: list[str]) -> dict[str, int]:
    return {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables}


def show(title: str, data: dict[str, int]) -> None:
    print(f"\n{title}")
    for t, n in data.items():
        print(f"  {t:<28} {n}")


def guard(args: argparse.Namespace) -> None:
    if args.dry_run:
        return
    if args.confirm != CONFIRM_PHRASE:
        sys.exit(f"Refusing: pass --confirm {CONFIRM_PHRASE} to clean the database for UAT.")
    if get_settings().app_env == "production" and not (
        args.allow_production and os.environ.get("UAT_RESET_ALLOW_PRODUCTION") == "yes"
    ):
        sys.exit("Refusing to clean a production database: requires --allow-production and "
                 "UAT_RESET_ALLOW_PRODUCTION=yes.")


def run(args: argparse.Namespace) -> None:
    guard(args)
    keep, wipe = plan()
    engine = get_engine()
    with engine.connect() as conn:
        show("KEPT (unchanged):", counts(conn, keep))
        show("DELETED (emptied):", counts(conn, wipe))
        active = conn.execute(text("SELECT count(*) FROM products WHERE is_active")).scalar()
    print(f"\nThen: {UNITS_PER_SKU} units of each of the {active} active SKU(s) are put in the default warehouse.")
    if args.dry_run:
        print("\nDry run: nothing changed.")
        return

    db = session_factory()()
    try:
        # One transaction: either everything is cleaned and restocked, or nothing changes.
        db.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in wipe) + " RESTART IDENTITY"))
        warehouse = default_warehouse(db)
        opening = system_location(db, LocationType.OPENING)
        products = db.execute(select(Product).where(Product.is_active).order_by(Product.id)).scalars().all()
        if products:
            ledger = Ledger(db, TxnType.OPENING_BALANCE, actor_id=None, ref=Ref("location", warehouse.id, warehouse.code),
                            reason="UAT starting stock")
            for p in products:
                ledger.move(p.id, opening, warehouse, UNITS_PER_SKU)
        record_audit(db, actor_id=None, action="system.uat_reset", entity_type="system", entity_id=None,
                     summary=f"Database cleaned for UAT; {UNITS_PER_SKU} units of {len(products)} SKU(s) "
                             f"put in {warehouse.code}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    with engine.connect() as conn:
        show("After clean-up — kept:", counts(conn, keep))
        show("After clean-up — operational tables:", counts(conn, wipe))
    print(f"\nDone: {len(products)} SKU(s) × {UNITS_PER_SKU} units in {warehouse.code}. Ready for UAT.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean the database for UAT (destructive).")
    parser.add_argument("--confirm", help=f"must be exactly {CONFIRM_PHRASE}")
    parser.add_argument("--dry-run", action="store_true", help="show what would be kept and deleted only")
    parser.add_argument("--allow-production", action="store_true",
                        help="also requires UAT_RESET_ALLOW_PRODUCTION=yes")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
