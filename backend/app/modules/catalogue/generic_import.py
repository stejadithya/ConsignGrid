"""Product master import, template and export for every Industry Pack except tyres (which keeps importer.py).

The columns come from the pack: SKU Code, the brand and name fields under the pack's labels ("Manufacturer",
"Device"…), Description, Barcode, Active, then one column per pack attribute ("REF", "Size", "Sterile"…).
Same two-phase workflow and result shape as the tyre importer: `analyse()` checks without changing anything, `apply()`
writes the valid rows. Prices are not imported (managed in the accounting system) and no stock is ever created.
"""

import io
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError
from app.core.industry import IndustryPack, current_pack
from app.modules.audit.service import record_audit
from app.modules.catalogue.attributes import AttributeError_, clean_attributes, display_value, is_blank
from app.modules.catalogue.importer import MAX_ROWS, PRICES_IGNORED, SKU_RE, RowResult, _norm, _text
from app.modules.catalogue.models import Product
from app.modules.identity.models import User

YELLOW = PatternFill("solid", fgColor="FDDA00")
GREY = PatternFill("solid", fgColor="EDEDED")
PRICE_HEADERS = ("dealerprice", "listprice", "price", "rrp", "costprice", "cost", "unitprice")


def columns(pack: IndustryPack) -> list[dict[str, Any]]:
    """Template columns: key, header, required, example, help, width, type."""
    cols = [
        {"key": "sku", "header": "SKU Code", "required": True, "example": "100001", "width": 14,
         "help": "Unique product code. Letters, digits, . _ / - (no spaces)."},
        {"key": "pattern", "header": pack.name_label, "required": True, "example": "", "width": 28,
         "help": f"The {pack.name_label.lower()} as people know it."},
        {"key": "brand", "header": pack.brand_label, "required": True, "example": "", "width": 18, "help": ""},
        {"key": "description", "header": "Description", "required": False, "example": "", "width": 36,
         "help": "Optional longer description."},
        {"key": "barcode", "header": "Barcode", "required": False, "example": "", "width": 16,
         "help": "Optional — EAN/GTIN; must be unique."},
        {"key": "active", "header": "Active (Y/N)", "required": False, "example": "Y", "width": 11,
         "help": "Optional — N hides the product from new transactions. Blank = Y."},
    ]
    for a in pack.attributes:
        if a.column:
            continue
        help_text = a.help
        if a.type == "choice":
            help_text = (help_text + " " if help_text else "") + f"One of: {', '.join(a.options)}."
        elif a.type == "boolean":
            help_text = (help_text + " " if help_text else "") + "Y or N."
        header = f"{a.label} ({a.unit})" if a.unit else a.label
        cols.append({"key": f"attr:{a.key}", "header": header, "required": a.required, "example": a.example,
                     "width": max(12, min(30, len(header) + 4)), "help": help_text.strip(), "type": a.type,
                     "options": a.options})
    return cols


def build_template(pack: IndustryPack | None = None) -> bytes:
    pack = pack or current_pack()
    cols = columns(pack)
    wb = Workbook()
    ws = wb.active
    ws.title = "SKUs"
    for i, c in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=i, value=c["header"])
        cell.font = Font(bold=True, color="18181B")
        cell.fill = YELLOW if c["required"] else GREY
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = c["width"]
        if c["key"] == "sku":
            for row in range(2, 2002):
                ws[f"{cell.column_letter}{row}"].number_format = "@"
        options = ("Y", "N") if c["key"] == "active" or c.get("type") == "boolean" else c.get("options")
        if options:
            dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{cell.column_letter}2:{cell.column_letter}2001")
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"

    name = get_settings().app_display_name
    info = wb.create_sheet("Instructions")
    info.column_dimensions["A"].width = 34
    info.column_dimensions["B"].width = 28
    info.column_dimensions["C"].width = 80
    info["A1"] = f"{name} — Product (SKU) import template · {pack.name}"
    info["A1"].font = Font(bold=True, size=14)
    lines = [
        "Fill one row per SKU on the 'SKUs' sheet. Keep the header row exactly as it is.",
        "Yellow columns are required. Grey columns are optional.",
        f"Upload the file in {name}: Products → Import products → Check file → Import.",
        "New SKU codes are created; existing SKU codes have their details updated.",
        "There are no price columns: prices are managed in the accounting system.",
        "Importing products never creates stock: stock is added by receiving goods or posting opening balances.",
    ]
    for i, line in enumerate(lines, start=3):
        info.cell(row=i, column=1, value=line)
    for col, title in enumerate(("Column", "Example", "Notes"), start=1):
        info.cell(row=10, column=col, value=title).font = Font(bold=True)
    for i, c in enumerate(cols, start=11):
        info.cell(row=i, column=1, value=f"{c['header']}{'  (required)' if c['required'] else ''}")
        info.cell(row=i, column=2, value=c["example"] or None)
        info.cell(row=i, column=3, value=c["help"] or None)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_export(products, pack: IndustryPack | None = None) -> bytes:
    """Every product in the template layout, so the file can be edited and imported again."""
    pack = pack or current_pack()
    cols = columns(pack)
    wb = load_workbook(io.BytesIO(build_template(pack)))
    ws = wb["SKUs"]
    defs = {a.key: a for a in pack.attributes}
    for row, p in enumerate(sorted(products, key=lambda x: x.sku), start=2):
        for col, c in enumerate(cols, start=1):
            key = c["key"]
            if key.startswith("attr:"):
                a = defs[key[5:]]
                v = (p.attributes or {}).get(a.key)
                value = ("Y" if v else "N") if a.type == "boolean" and v is not None else v
            elif key == "active":
                value = "Y" if p.is_active else "N"
            else:
                value = getattr(p, key)
            ws.cell(row=row, column=col, value=value)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _header_map(pack: IndustryPack) -> dict[str, str]:
    """Normalised header → column key, accepting the pack labels and common synonyms."""
    out: dict[str, str] = {}
    for c in columns(pack):
        out[_norm(c["header"])] = c["key"]
        if c["key"].startswith("attr:"):
            a = pack.attribute(c["key"][5:])
            out[_norm(a.label)] = c["key"]
            out[_norm(a.key)] = c["key"]
    for alias, key in (("sku", "sku"), ("skucode", "sku"), ("productcode", "sku"), ("itemcode", "sku"),
                       ("partnumber", "sku"), ("code", "sku"), ("name", "pattern"), ("productname", "pattern"),
                       ("model", "pattern"), ("brand", "brand"), ("manufacturer", "brand"),
                       ("description", "description"), ("skudescription", "description"), ("barcode", "barcode"),
                       ("ean", "barcode"), ("gtin", "barcode"), ("active", "active"), ("activeyn", "active")):
        out.setdefault(alias, key)
    return out


def _read_rows(content: bytes, pack: IndustryPack):
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any parsing failure means "not a usable .xlsx"
        raise BusinessRuleError("The file could not be read as an Excel workbook (.xlsx).") from exc
    names = _header_map(pack)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 20))
        for idx, row in enumerate(rows[:15]):
            cols: dict[str, int] = {}
            prices = False
            for c, cell in enumerate(row):
                n = _norm(cell)
                key = names.get(n)
                if key and key not in cols:
                    cols[key] = c
                elif n and any(n.startswith(h) for h in PRICE_HEADERS):
                    prices = True
            if {"sku", "pattern"} <= cols.keys():
                return ws.title, idx + 1, cols, prices, [(idx + 2 + i, list(r)) for i, r in enumerate(rows[idx + 1:])]
    raise BusinessRuleError(f"No header row found. The sheet needs the columns 'SKU Code' and '{pack.name_label}' — "
                            "download the template from Products → Import products.")


UPDATABLE = ("brand", "pattern", "description", "barcode", "is_active", "attributes")


def analyse(db: Session, content: bytes) -> dict[str, Any]:
    pack = current_pack()
    sheet, header_row, cols, prices, data = _read_rows(content, pack)
    existing = {p.sku: p for p in db.execute(select(Product)).scalars()}
    barcodes = {p.barcode: p.sku for p in existing.values() if p.barcode}
    labels = {"brand": pack.brand_label, "pattern": pack.name_label, "description": "Description",
              "barcode": "Barcode", "is_active": "Active"}
    seen: dict[str, int] = {}
    results: list[RowResult] = []

    def cell(r: list[Any], key: str) -> Any:
        i = cols.get(key)
        return r[i] if i is not None and i < len(r) else None

    for rownum, r in data:
        if all(is_blank(cell(r, k)) for k in cols):
            continue
        sku = _text(cell(r, "sku")).upper()
        name = _text(cell(r, "pattern"))
        if len(results) >= MAX_ROWS:
            raise BusinessRuleError(f"Too many rows: the limit is {MAX_ROWS} per file.")
        res = RowResult(row=rownum, sku=sku, description=_text(cell(r, "description")) or name)
        results.append(res)
        v = res.values
        if not sku:
            res.errors.append("SKU Code is missing")
        elif not SKU_RE.match(sku) or len(sku) > 50:
            res.errors.append(f"SKU Code '{sku}' is not valid (letters, digits, . _ / - only, no spaces)")
        elif sku in seen:
            res.errors.append(f"SKU {sku} appears more than once in this file (first on row {seen[sku]})")
        else:
            seen[sku] = rownum
        v["pattern"] = name or None
        v["brand"] = _text(cell(r, "brand")) or None
        for key in ("pattern", "brand"):
            if not v[key]:
                res.errors.append(f"{labels[key]} is missing")
        if "description" in cols:
            v["description"] = _text(cell(r, "description")) or None
        if "barcode" in cols:
            v["barcode"] = _text(cell(r, "barcode")) or None
            if v["barcode"] and barcodes.get(v["barcode"], sku) != sku:
                res.errors.append(f"Barcode {v['barcode']} already belongs to SKU {barcodes[v['barcode']]}")
        if "active" in cols:
            active = _norm(cell(r, "active"))
            v["is_active"] = active not in ("n", "no", "false", "0", "inactive") if active else True
        raw = {k[5:]: _text(cell(r, k)) for k in cols if k.startswith("attr:")}
        try:
            v["attributes"] = clean_attributes(pack, raw)
        except AttributeError_ as exc:
            res.errors.extend(str(exc).split("; "))
        v["spec"] = " · ".join(display_value(a, v.get("attributes", {}).get(a.key))
                               for a in pack.attributes if a.in_spec and v.get("attributes", {}).get(a.key) is not None)

        if res.errors:
            res.action = "error"
            continue
        current = existing.get(sku)
        if current is None:
            res.action = "create"
            continue
        if current.has_tyre_size:
            res.errors.append(f"SKU {sku} is a tyre in the catalogue; it cannot be updated by this import")
            res.action = "error"
            continue
        for key in UPDATABLE:
            if key not in v:
                continue
            old, new = getattr(current, key), v[key]
            if key == "attributes":
                if (old or {}) != new:
                    res.changes.append("Attributes: " + ", ".join(
                        f"{pack.attribute(k).label} {old.get(k, '—') if old else '—'} → {new.get(k, '—')}"
                        for k in sorted(set(old or {}) | set(new)) if (old or {}).get(k) != new.get(k)))
            elif new is not None and old != new:
                res.changes.append(f"{labels[key]}: {old if old is not None else '—'} → {new}")
        res.action = "update" if res.changes else "unchanged"

    summary = {a: sum(1 for x in results if x.action == a) for a in ("create", "update", "unchanged", "error")}
    summary["total"] = len(results)
    rows = []
    for x in results:
        row = x.out()
        row["size"] = x.values.get("spec") or None
        row["attributes"] = x.values.get("attributes", {})
        rows.append(row)
    return {"sheet": sheet, "header_row": header_row, "columns": sorted(cols), "summary": summary,
            "notes": [PRICES_IGNORED.replace("Xero", "the accounting system")] if prices else [],
            "rows": rows, "_results": results}


def apply(db: Session, actor: User, analysis: dict[str, Any], filename: str | None) -> dict[str, int]:
    existing = {p.sku: p for p in db.execute(select(Product).with_for_update()).scalars()}
    created = updated = 0
    for res in analysis["_results"]:
        v = res.values
        if res.action == "create":
            db.add(Product(sku=res.sku, brand=v["brand"], pattern=v["pattern"], description=v.get("description"),
                           barcode=v.get("barcode"), is_active=v.get("is_active", True),
                           attributes=v.get("attributes", {})))
            created += 1
        elif res.action == "update":
            product = existing[res.sku]
            for key in UPDATABLE:
                if key in v and (v[key] is not None or key == "attributes"):
                    setattr(product, key, v[key])
            updated += 1
    db.flush()
    s = analysis["summary"]
    record_audit(db, actor_id=actor.id, action="product.import", entity_type="product", entity_id=None,
                 summary=f"Imported product master{f' from {filename}' if filename else ''}: {created} created, "
                         f"{updated} updated, {s['unchanged']} unchanged, {s['error']} rows skipped with errors",
                 details={"filename": filename, "created": created, "updated": updated,
                          "unchanged": s["unchanged"], "errors": s["error"], "pack": current_pack().code})
    return {"created": created, "updated": updated, "unchanged": s["unchanged"], "skipped": s["error"]}
