"""Release 1.11, finding 15: export every SKU in the import template layout, edit, and import again."""

import base64
import io
from datetime import date

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.modules.audit.models import AuditEvent

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled

LAYOUT = ["SKU Code", "SKU Description", "Brand", "Pattern", "Width (mm)", "Aspect Ratio", "Rim Diameter (in)",
          "Load Index", "Speed Rating", "Barcode", "Active (Y/N)"]


def _export(world, who):
    r = world.api(who).get("/products/export")
    assert r.headers["content-disposition"].endswith(f'filename="TyreGrow_SKUs_{date.today().isoformat()}.xlsx"')
    return r.content


def _reimport(world, content, commit=False):
    return world.api(world.warehouse_op).post("/products/import", {
        "filename": "export.xlsx", "content_base64": base64.b64encode(content).decode(), "commit": commit}).json()


def test_export_layout_includes_inactive_sorted_by_sku(world):
    world.p3.is_active = False
    world.db.commit()
    ws = load_workbook(io.BytesIO(_export(world, world.manager)))["SKUs"]
    rows = [[c.value for c in r] for r in ws.iter_rows() if r[0].value]
    assert rows[0] == LAYOUT
    assert [r[0] for r in rows[1:]] == sorted(r[0] for r in rows[1:]) == ["TYR-001", "TYR-002", "TYR-003"]
    assert rows[3][10] == "N" and rows[1][10] == "Y"
    assert world.db.execute(select(AuditEvent).where(AuditEvent.action == "product.export")).scalars().one()


def test_reimport_unchanged_then_edit_then_new_row(world):
    content = _export(world, world.warehouse_op)
    check = _reimport(world, content)
    assert check["summary"]["error"] == 0 and check["summary"]["update"] == 0 and check["summary"]["create"] == 0
    assert {r["action"] for r in check["rows"]} == {"unchanged"}     # "No change" on screen

    wb = load_workbook(io.BytesIO(content))
    ws = wb["SKUs"]
    assert ws["A2"].value == "TYR-001"
    ws["B2"] = "205/55R16 PRIMACY 4 TL 91V MICHELIN (edited)"
    for col, value in enumerate(["TYR-NEW", "215/60R16 ECODRIVE TL 95H CEAT", "CEAT", "ECODRIVE", 215, 60, 16, "95", "H",
                                 None, "Y"], start=1):
        ws.cell(row=5, column=col, value=value)
    buf = io.BytesIO()
    wb.save(buf)
    edited = _reimport(world, buf.getvalue(), commit=True)
    by_sku = {r["sku"]: r["action"] for r in edited["rows"]}
    assert by_sku["TYR-001"] == "update" and by_sku["TYR-NEW"] == "create" and by_sku["TYR-002"] == "unchanged"
    assert edited["result"]["created"] == 1 and edited["result"]["updated"] == 1


def test_export_permissions(world):
    world.api(world.admin).get("/products/export")       # Relationship Manager
    world.api(world.rep).get("/products/export", expected=403)
    world.api(world.user_a).get("/products/export", expected=403)
