"""The standard blank Excel template for the product master (download from Products → Import products)."""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.core.config import get_settings

# (header, width, required, example, help)
TEMPLATE_COLUMNS = [
    ("SKU Code", 14, True, "700001", "Unique product code. Letters, digits, . _ / - (no spaces)."),
    ("SKU Description", 46, True, "175/65R14 ECOTRAIL TL 82T NORDWAY",
     "Full description. Size, pattern, load/speed and brand are read from it when the optional columns are blank."),
    ("Brand", 14, False, "NORDWAY", "Optional — read from the description if blank (last word)."),
    ("Pattern", 20, False, "ECOTRAIL", "Optional — read from the description if blank."),
    ("Width (mm)", 11, False, 175, "Optional — e.g. 175."),
    ("Aspect Ratio", 12, False, 65, "Optional — e.g. 65."),
    ("Rim Diameter (in)", 14, False, 14, "Optional — e.g. 14 or 17.5."),
    ("Load Index", 11, False, "82", "Optional — e.g. 82 or 106/104."),
    ("Speed Rating", 12, False, "T", "Optional — e.g. T, H, V, W, Y."),
    ("Barcode", 16, False, None, "Optional — EAN/GTIN; must be unique."),
    ("Active (Y/N)", 11, False, "Y", "Optional — N hides the product from new transactions. Blank = Y."),
]

YELLOW = PatternFill("solid", fgColor="FDDA00")
GREY = PatternFill("solid", fgColor="EDEDED")


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "SKUs"
    for col, (header, width, required, _example, _help) in enumerate(TEMPLATE_COLUMNS, start=1):
        c = ws.cell(row=1, column=col, value=header)
        c.font = Font(bold=True, color="18181B")
        c.fill = YELLOW if required else GREY
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = width
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"
    headers = [h for h, *_ in TEMPLATE_COLUMNS]
    text_cols = (headers.index("SKU Code") + 1, headers.index("Load Index") + 1)
    for col in text_cols:                     # SKU and load index stay text (keep leading zeros, 106/104)
        letter = ws.cell(row=1, column=col).column_letter
        for row in range(2, 2002):
            ws[f"{letter}{row}"].number_format = "@"
    yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    ws.add_data_validation(yn)
    active = ws.cell(row=1, column=headers.index("Active (Y/N)") + 1).column_letter
    yn.add(f"{active}2:{active}2001")

    info = wb.create_sheet("Instructions")
    info.column_dimensions["A"].width = 40
    info.column_dimensions["B"].width = 34
    info.column_dimensions["C"].width = 90
    info["A1"] = f"{get_settings().app_display_name} — Product (SKU) import template"
    info["A1"].font = Font(bold=True, size=14)
    lines = [
        "Fill one row per SKU on the 'SKUs' sheet. Keep the header row exactly as it is.",
        "Yellow columns are required. Grey columns are optional.",
        f"Upload the file in {get_settings().app_display_name}: Products → Import products → Check file → Import.",
        "New SKU codes are created; existing SKU codes have their description and details updated.",
        "There are no price columns: prices are managed in Xero. Price columns in older files are ignored.",
        "Tyre size cannot be changed by an import. Rows with errors are skipped and listed before you confirm.",
        "Importing products never creates stock: stock is added by receiving goods or posting opening balances.",
    ]
    for i, line in enumerate(lines, start=3):
        info.cell(row=i, column=1, value=line)
    info.cell(row=10, column=1, value="Column").font = Font(bold=True)
    info.cell(row=10, column=2, value="Example").font = Font(bold=True)
    info.cell(row=10, column=3, value="Notes").font = Font(bold=True)
    for i, (header, _w, required, example, help_text) in enumerate(TEMPLATE_COLUMNS, start=11):
        info.cell(row=i, column=1, value=f"{header}{'  (required)' if required else ''}")
        info.cell(row=i, column=2, value=example)
        info.cell(row=i, column=3, value=help_text)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_export(products) -> bytes:
    """Every product in exactly the import template layout, so the file can be edited and imported again (finding 15).
    A product without its own description is exported with its display name (the importer treats that as unchanged)."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(build_template()))
    ws = wb["SKUs"]
    # Write from row 2 (the template pre-formats its rows, so append() would start below them).
    for row, p in enumerate(sorted(products, key=lambda x: x.sku), start=2):
        rim = int(p.rim_diameter) if p.rim_diameter == int(p.rim_diameter) else float(p.rim_diameter)
        values = [p.sku, p.description or p.display_name, p.brand, p.pattern, p.width, p.aspect_ratio, rim,
                  p.load_index, p.speed_rating, p.barcode, "Y" if p.is_active else "N"]
        for col, value in enumerate(values, start=1):
            ws.cell(row=row, column=col, value=value)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
