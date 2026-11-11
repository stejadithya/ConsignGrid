"""Initial stock of an existing dealer from Excel (finding 13).

check()  reads the workbook and validates every row WITHOUT changing anything.
commit() posts one opening balance per shop through the existing post_opening_balance, so the ledger stays the
         single source of truth. Columns: SKU Code · Quantity · Shop code (optional when the dealer has one shop).
"""

import io
import re
from collections import defaultdict
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.core.industry import vocab
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.identity.models import User
from app.modules.inventory.operations import post_opening_balance
from app.modules.inventory.schemas import OpeningBalanceIn, QtyLine

MAX_ROWS = 5000
REASON = "Initial stock (backorder): imported from Excel"


def headers() -> tuple[str, str, str]:
    """Column headers; the site column follows the Industry Pack ("Shop code", "Location code"…)."""
    return ("SKU Code", "Quantity", f"{vocab.Site} code")


def _names() -> dict[str, tuple[str, ...]]:
    site = _norm(vocab.site)
    return {"sku": ("skucode", "sku", "code"), "qty": ("quantity", "qty", "quantityheld"),
            "shop": ("shopcode", "shop", "location", "locationcode", site, site + "code")}


def template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Initial stock"
    cols = headers()
    for col, h in enumerate(cols, start=1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="FDDA00" if h != cols[2] else "EDEDED")
        ws.column_dimensions[c.column_letter].width = 18
    for row in range(2, 2002):
        ws[f"A{row}"].number_format = "@"
    ws["E1"] = (f"One row per {vocab.item} and {vocab.site}. {vocab.Site} code is optional when the {vocab.partner} "
                f"has a single {vocab.site}.")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def _text(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else str(v).strip()


def check(db: Session, reseller: Reseller, content: bytes) -> dict[str, Any]:
    try:
        ws = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
    except Exception as exc:  # noqa: BLE001 - any parsing failure means "not a usable .xlsx"
        raise BusinessRuleError("The file could not be read as an Excel workbook (.xlsx).") from exc
    rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 20))
    cols: dict[str, int] = {}
    header_at = None
    for idx, row in enumerate(rows[:10]):
        found = {key: c for c, cell in enumerate(row) for key, names in _names().items() if _norm(cell) in names}
        if "sku" in found and "qty" in found:
            cols, header_at = found, idx
            break
    if header_at is None:
        raise BusinessRuleError("No header row found. The sheet needs 'SKU Code' and 'Quantity' — download the template.")
    shops = {loc.code: loc for loc in db.execute(select(Location).where(
        Location.reseller_id == reseller.id, Location.type == LocationType.CONSIGNMENT, Location.is_active.is_(True))).scalars()}
    only_shop = next(iter(shops.values())) if len(shops) == 1 else None
    products = {p.sku: p for p in db.execute(select(Product)).scalars()}
    seen: dict[tuple[str, str], int] = {}
    out: list[dict[str, Any]] = []
    for offset, r in enumerate(rows[header_at + 1:]):
        rownum = header_at + 2 + offset
        values = {k: (r[c] if c < len(r) else None) for k, c in cols.items()}
        sku, qty_raw = _text(values.get("sku")).upper(), _text(values.get("qty"))
        shop_code = _text(values.get("shop")).upper()
        if not sku and not qty_raw and not shop_code:
            continue
        if len(out) >= MAX_ROWS:
            raise BusinessRuleError(f"Too many rows: the limit is {MAX_ROWS} per file.")
        errors: list[str] = []
        product = products.get(sku)
        if not sku:
            errors.append("SKU Code is missing")
        elif product is None:
            errors.append(f"Unknown SKU {sku}")
        elif not product.is_active:
            errors.append(f"SKU {sku} is inactive")
        try:
            qty = int(float(qty_raw))
            if qty <= 0 or float(qty_raw) != qty:
                raise ValueError
        except ValueError:
            qty = 0
            errors.append(f"Quantity '{qty_raw}' must be a whole number above 0")
        shop = shops.get(shop_code) if shop_code else only_shop
        if shop is None:
            errors.append(f"Unknown {vocab.site} {shop_code}" if shop_code
                          else f"{vocab.Site} code is needed: this {vocab.partner} has more than one {vocab.site}")
        if shop and sku:
            key = (shop.code, sku)
            if key in seen:
                errors.append(f"SKU {sku} appears more than once for {vocab.site} {shop.code} (first on row {seen[key]})")
            else:
                seen[key] = rownum
        out.append({"row": rownum, "sku": sku, "product_id": product.id if product else None,
                    "tyre": product.display_name if product else None, "quantity": qty,
                    "shop_code": shop.code if shop else shop_code or None, "location_id": shop.id if shop else None,
                    "errors": errors})
    valid = [x for x in out if not x["errors"]]
    return {"rows": out, "summary": {"total": len(out), "valid": len(valid), "errors": len(out) - len(valid),
                                     "units": sum(x["quantity"] for x in valid)}}


def commit(db: Session, actor: User, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Post the valid rows: one opening balance per shop. Refuses if any row has an error."""
    if analysis["summary"]["errors"]:
        raise BusinessRuleError("Fix the rows with errors first; nothing was imported.")
    by_shop: dict[int, list[QtyLine]] = defaultdict(list)
    for x in analysis["rows"]:
        by_shop[x["location_id"]].append(QtyLine(product_id=x["product_id"], quantity=x["quantity"]))
    posted = []
    for location_id, lines in by_shop.items():
        txn = post_opening_balance(db, actor, OpeningBalanceIn(location_id=location_id, lines=lines), reason=REASON)
        posted.append({"location_id": location_id, "transaction_number": txn.number, "units": sum(ln.quantity for ln in lines)})
    return posted
