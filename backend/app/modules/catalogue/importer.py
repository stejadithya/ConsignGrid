"""Product master import from Excel (the TyreGrow SKU template, or the dealer price list layout).

Workflow: `analyse()` reads the workbook and checks every row against the catalogue WITHOUT changing anything;
`apply()` then creates new SKUs and updates existing ones for the valid rows only, in one transaction.

Only products are written. A product in the catalogue never creates stock: warehouse and consignment stock stay
at zero until goods are received, delivered or posted as opening balances.

Columns (header names are matched case-insensitively; the header row may sit below title lines):
  required  SKU Code · SKU Description
  optional  Brand · Pattern · Width · Aspect Ratio · Rim Diameter · Load Index · Speed Rating · Barcode · Active (Y/N)
Price columns (Dealer Price, RRP, Cost Price), if present, are ignored: prices are managed in Xero (D2).
Blank optional size/brand/pattern/load/speed columns are read from the SKU description, e.g.
"205/55R16 ECODRIVE TL 91H CEAT" → width 205, aspect 55, rim 16, pattern ECODRIVE, load 91, speed H, brand CEAT.
"""

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.modules.audit.service import record_audit
from app.modules.catalogue.models import Product
from app.modules.identity.models import User

MAX_ROWS = 5000
SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
# 205/55R16, 205/55 R16, 205/55ZR17, 195R15C (no aspect ratio: commercial/metric sizes)
SIZE_RE = re.compile(r"\b(\d{3})(?:/(\d{2,3}))?\s?(ZR|R|D|B|-)\s?(\d{2}(?:\.\d)?)(C)?\b")
LOAD_SPEED_RE = re.compile(r"^(\d{2,3}(?:/\d{2,3})?)([A-Z]{1,2})$")
NON_PATTERN = {"TL", "TT", "XL", "RF", "RFT", "C"}

# Canonical field → accepted header spellings (normalised: lower case, letters/digits only).
COLUMNS: dict[str, tuple[str, ...]] = {
    "sku": ("skucode", "sku", "productcode", "itemcode", "code"),
    "description": ("skudescription", "description", "productdescription", "itemdescription"),
    "dealer_price": ("dealerprice", "dealerpriceexclgststewardship", "dealerpriceexclgstandstewardship", "listprice"),
    "rrp": ("rrp", "rrpinclgstbutexclstewardship", "rrpinclgstexclstewardship", "recommendedretailprice"),
    "brand": ("brand",),
    "pattern": ("pattern", "patternmodel", "model"),
    "width": ("width", "widthmm"),
    "aspect_ratio": ("aspectratio", "profile", "aspect"),
    "rim_diameter": ("rimdiameter", "rim", "rimdiameterin", "rimin"),
    "load_index": ("loadindex", "load"),
    "speed_rating": ("speedrating", "speed"),
    "barcode": ("barcode", "ean", "gtin"),
    "cost_price": ("costprice", "costpriceexclgst", "cost"),
    "active": ("active", "activeyn", "status"),
}
REQUIRED = ("sku", "description")
UPDATABLE = ("brand", "pattern", "load_index", "speed_rating", "description", "barcode", "is_active")
PRICE_COLUMNS = ("dealer_price", "rrp", "cost_price")
PRICES_IGNORED = "Price columns are ignored: prices are managed in Xero"


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _match_header(cell: Any) -> str | None:
    n = _norm(cell)
    if not n:
        return None
    for key, names in COLUMNS.items():
        if n in names:
            return key
    # Long descriptive headers ("Dealer Price (excl. GST & Stewardship)", "RRP (incl. GST …)").
    for key, prefix in (("dealer_price", "dealerprice"), ("rrp", "rrp"), ("cost_price", "costprice"),
                        ("description", "skudescription"), ("active", "active")):
        if n.startswith(prefix):
            return key
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def parse_description(desc: str) -> dict[str, Any]:
    """Read size, pattern, load index, speed rating and brand from a tyre description. Missing parts are omitted."""
    out: dict[str, Any] = {}
    text = " ".join(desc.upper().split())
    m = SIZE_RE.search(text)
    if not m:
        return out
    width, aspect, construction, rim, commercial = m.groups()
    out.update(width=int(width), rim_diameter=Decimal(rim), construction="R" if construction == "ZR" else construction)
    if aspect:
        out["aspect_ratio"] = int(aspect)
    else:
        out["aspect_ratio_assumed"] = True       # e.g. 195R15C: metric size without a stated profile
    if commercial:
        out["commercial"] = True
    tokens = text[m.end():].split()
    pattern: list[str] = []
    for i, tok in enumerate(tokens):
        ls = LOAD_SPEED_RE.match(tok)
        if ls:
            out["load_index"], out["speed_rating"] = ls.group(1), ls.group(2)
            rest = [t for t in tokens[i + 1:] if t not in NON_PATTERN]
            if rest:
                out["brand"] = rest[-1]
            break
        if tok in NON_PATTERN:
            continue
        if not out.get("load_index"):
            pattern.append(tok)
    if "brand" not in out and tokens and tokens[-1] not in NON_PATTERN and not LOAD_SPEED_RE.match(tokens[-1]):
        out["brand"] = tokens[-1]
        if pattern and pattern[-1] == tokens[-1]:
            pattern.pop()
    if pattern:
        out["pattern"] = " ".join(pattern)
    return out


@dataclass
class RowResult:
    row: int
    sku: str
    description: str
    action: str = "create"            # create | update | unchanged | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)

    def out(self) -> dict[str, Any]:
        v = self.values
        size = (f"{v['width']}/{v['aspect_ratio']}{v.get('construction', 'R')}{_rim(v['rim_diameter'])}"
                if {"width", "aspect_ratio", "rim_diameter"} <= v.keys() else None)
        return {"row": self.row, "sku": self.sku, "description": self.description, "action": self.action,
                "errors": self.errors, "warnings": self.warnings, "changes": self.changes,
                "brand": v.get("brand"), "pattern": v.get("pattern"), "size": size,
                "load_index": v.get("load_index"), "speed_rating": v.get("speed_rating")}


def _rim(r: Decimal) -> str:
    return str(int(r)) if r == int(r) else str(r)


def _read_rows(content: bytes) -> tuple[str, int, dict[str, int], list[tuple[int, list[Any]]]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any parsing failure means "not a usable .xlsx"
        raise BusinessRuleError("The file could not be read as an Excel workbook (.xlsx).") from exc
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 20))
        for idx, row in enumerate(rows[:15]):
            cols: dict[str, int] = {}
            for c, cell in enumerate(row):
                key = _match_header(cell)
                if key and key not in cols:
                    cols[key] = c
            if all(k in cols for k in REQUIRED):
                data = [(idx + 2 + i, list(r)) for i, r in enumerate(rows[idx + 1:])]
                return ws.title, idx + 1, cols, data
    raise BusinessRuleError("No header row found. The sheet needs the columns 'SKU Code' and 'SKU Description' — "
                            "download the template from Products → Import products.")


def analyse(db: Session, content: bytes) -> dict[str, Any]:
    sheet, header_row, cols, data = _read_rows(content)
    existing = {p.sku: p for p in db.execute(select(Product)).scalars()}
    barcodes = {p.barcode: p.sku for p in existing.values() if p.barcode}
    seen: dict[str, int] = {}
    results: list[RowResult] = []

    def cell(r: list[Any], key: str) -> Any:
        i = cols.get(key)
        return r[i] if i is not None and i < len(r) else None

    for rownum, r in data:
        sku, desc = _text(cell(r, "sku")).upper(), _text(cell(r, "description"))
        if not sku and not desc and all(cell(r, k) in (None, "") for k in cols):
            continue                                            # blank line
        if sku and not SKU_RE.match(sku) and not desc and all(cell(r, k) in (None, "") for k in cols
                                                              if k != "sku" and k not in PRICE_COLUMNS):
            continue                                            # a free-text note written in the SKU column
        if len(results) >= MAX_ROWS:
            raise BusinessRuleError(f"Too many rows: the limit is {MAX_ROWS} per file.")
        res = RowResult(row=rownum, sku=sku, description=desc)
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
        if not desc:
            res.errors.append("SKU Description is missing")

        parsed = parse_description(desc) if desc else {}
        for key in ("brand", "pattern", "load_index", "speed_rating"):
            given = _text(cell(r, key))
            v[key] = given.upper() if key == "speed_rating" else given or None
            if not v[key] and parsed.get(key):
                v[key] = parsed[key]
        for key, conv in (("width", int), ("aspect_ratio", int), ("rim_diameter", Decimal)):
            given = _text(cell(r, key))
            if given:
                try:
                    v[key] = conv(given)
                except (ValueError, InvalidOperation):
                    res.errors.append(f"{key.replace('_', ' ').title()} '{given}' is not a number")
            elif key in parsed:
                v[key] = parsed[key]
        v["construction"] = parsed.get("construction", "R")
        if "aspect_ratio" not in v and parsed.get("aspect_ratio_assumed") and "width" in v:
            v["aspect_ratio"] = 80
            res.warnings.append("No aspect ratio in the size; 80 assumed (standard for metric commercial sizes)")
        missing = [k for k in ("width", "aspect_ratio", "rim_diameter") if k not in v]
        if missing and desc:
            res.errors.append("Tyre size not found in the description (expected e.g. 205/55R16); "
                              "fill Width, Aspect Ratio and Rim Diameter")
        for key, label in (("brand", "Brand"), ("pattern", "Pattern"), ("load_index", "Load index"),
                           ("speed_rating", "Speed rating")):
            if not v.get(key) and desc and not missing:
                res.errors.append(f"{label} not found in the description; fill the {label} column")
        v["barcode"] = _text(cell(r, "barcode")) or None
        if v["barcode"] and barcodes.get(v["barcode"], sku) != sku:
            res.errors.append(f"Barcode {v['barcode']} already belongs to SKU {barcodes[v['barcode']]}")
        active = _norm(cell(r, "active"))
        v["is_active"] = active not in ("n", "no", "false", "0", "inactive") if active else True
        v["description"] = desc or None
        if "barcode" not in cols:
            v.pop("barcode", None)
        if "active" not in cols:
            v.pop("is_active", None)

        if res.errors:
            res.action = "error"
            continue
        current = existing.get(sku)
        if current is None:
            res.action = "create"
            continue
        if (current.width, current.aspect_ratio, current.rim_diameter) != (v["width"], v["aspect_ratio"], v["rim_diameter"]):
            res.warnings.append(f"Size in file ({v['width']}/{v['aspect_ratio']}R{_rim(v['rim_diameter'])}) differs from the "
                                f"catalogue ({current.size_display}); size is not changed by an import")
        if current.description is None and v.get("description") == current.display_name:
            v.pop("description")   # an exported file carries the display name for products without a description
        for key in UPDATABLE:
            old = getattr(current, key)
            if key in v and v[key] is not None and old != v[key]:
                res.changes.append(f"{CHANGE_LABELS[key]}: {old if old is not None else '—'} → {v[key]}")
        res.action = "update" if res.changes else "unchanged"

    summary = {a: sum(1 for x in results if x.action == a) for a in ("create", "update", "unchanged", "error")}
    summary["total"] = len(results)
    notes = [PRICES_IGNORED] if any(k in cols for k in PRICE_COLUMNS) else []
    return {"sheet": sheet, "header_row": header_row, "columns": sorted(k for k in cols if k not in PRICE_COLUMNS),
            "summary": summary, "notes": notes, "rows": [x.out() for x in results], "_results": results}


CHANGE_LABELS = {"brand": "Brand", "pattern": "Pattern", "load_index": "Load index", "speed_rating": "Speed rating",
                 "description": "Description", "barcode": "Barcode", "is_active": "Active"}


def apply(db: Session, actor: User, analysis: dict[str, Any], filename: str | None) -> dict[str, int]:
    """Create/update the valid rows of an analysis. Error rows are skipped. Never creates stock."""
    existing = {p.sku: p for p in db.execute(select(Product).with_for_update()).scalars()}
    created = updated = 0
    for res in analysis["_results"]:
        v = res.values
        if res.action == "create":
            db.add(Product(sku=res.sku, brand=v["brand"], pattern=v["pattern"], width=v["width"],
                           aspect_ratio=v["aspect_ratio"], rim_diameter=v["rim_diameter"],
                           construction=v.get("construction", "R"), load_index=v["load_index"],
                           speed_rating=v["speed_rating"], description=v.get("description"),
                           barcode=v.get("barcode"), is_active=v.get("is_active", True)))
            created += 1
        elif res.action == "update":
            product = existing[res.sku]
            for key in UPDATABLE:
                if key in v and v[key] is not None:
                    setattr(product, key, v[key])
            updated += 1
    db.flush()
    s = analysis["summary"]
    record_audit(db, actor_id=actor.id, action="product.import", entity_type="product", entity_id=None,
                 summary=f"Imported product master{f' from {filename}' if filename else ''}: {created} created, "
                         f"{updated} updated, {s['unchanged']} unchanged, {s['error']} rows skipped with errors",
                 details={"filename": filename, "created": created, "updated": updated,
                          "unchanged": s["unchanged"], "errors": s["error"]})
    return {"created": created, "updated": updated, "unchanged": s["unchanged"], "skipped": s["error"]}
