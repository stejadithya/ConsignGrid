"""Import an Excel product master file from the command line (same rules as Products → Import products).

    python -m scripts.import_products data/products/sample-tyre-catalogue.xlsx          # check only
    python -m scripts.import_products data/products/sample-tyre-catalogue.xlsx --commit

Creates new SKUs and updates existing ones; rows with errors are skipped and listed. Never creates stock.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.db import session_factory
from app.core.errors import DomainError
from app.core.permissions import Role
from app.modules.catalogue import importer
from app.modules.identity.models import User


def run(path: str, commit: bool) -> dict:
    content = Path(path).read_bytes()
    db = session_factory()()
    try:
        try:
            analysis = importer.analyse(db, content)
        except DomainError as exc:
            sys.exit(f"Cannot import {path}: {exc}")
        s = analysis["summary"]
        print(f"{path} — sheet '{analysis['sheet']}', header on row {analysis['header_row']}")
        print(f"  new: {s['create']}  updated: {s['update']}  unchanged: {s['unchanged']}  errors: {s['error']}")
        for r in analysis["rows"]:
            for e in r["errors"]:
                print(f"  row {r['row']} ({r['sku'] or 'no SKU'}): ERROR {e}")
            for w in r["warnings"]:
                print(f"  row {r['row']} ({r['sku']}): note — {w}")
        if not commit:
            print("Check only: nothing changed. Add --commit to import the valid rows.")
            return analysis
        actor = db.execute(select(User).where(User.role == Role.ADMINISTRATOR, User.is_active.is_(True))
                           .order_by(User.id)).scalars().first() \
            or db.execute(select(User).where(User.role == Role.WAREHOUSE_MANAGER).order_by(User.id)).scalars().first()
        if actor is None:
            sys.exit("Create the Administrator or Warehouse Manager account first (the import is recorded against it).")
        result = importer.apply(db, actor, analysis, Path(path).name)
        db.commit()
        print(f"Imported: {result['created']} created, {result['updated']} updated, {result['skipped']} skipped. "
              "No stock was created.")
        return analysis
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an Excel product master file.")
    parser.add_argument("path")
    parser.add_argument("--commit", action="store_true", help="import the valid rows (default: check only)")
    args = parser.parse_args()
    run(args.path, args.commit)


if __name__ == "__main__":
    main()
