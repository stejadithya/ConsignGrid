"""Generic items (white-label step 1.4): every Industry Pack except tyres describes its items with its own attributes;
the tyres pack keeps the tyre columns, importer and size search unchanged."""

import base64
import io

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.core.config import get_settings
from app.core.industry import PACKS
from app.modules.catalogue.attributes import AttributeError_, clean_attributes
from app.modules.catalogue.models import Product
from app.modules.inventory.models import StockBalance


@pytest.fixture
def medical(monkeypatch):
    monkeypatch.setattr(get_settings(), "industry_pack", "medical")
    return PACKS["medical"]


SCREW = {"sku": "MED-001", "brand": "Orthex", "pattern": "Cortical screw",
         "attributes": {"ref": "71933215", "size": "4.5 x 30 mm", "sterile": "Y", "device_class": "iib"}}


def test_attributes_are_validated_and_converted():
    pack = PACKS["medical"]
    assert clean_attributes(pack, {"ref": " 7193 ", "sterile": "no", "size": ""}) == {"ref": "7193", "sterile": False}
    with pytest.raises(AttributeError_) as e:
        clean_attributes(pack, {"sterile": "maybe", "device_class": "IV", "colour": "red"})
    msg = str(e.value)
    assert "Unknown attribute(s): colour" in msg and "REF is required" in msg
    assert "Sterile must be Yes or No" in msg and "Class must be one of: I, IIa, IIb, III" in msg
    auto = PACKS["auto_parts"]
    assert clean_attributes(auto, {"category": "battery", "warranty_months": "24", "core_charge": "25.50"}) == \
        {"category": "Battery", "warranty_months": 24, "core_charge": "25.50"}
    with pytest.raises(AttributeError_, match="Warranty must be a whole number"):
        clean_attributes(auto, {"category": "Battery", "warranty_months": "2.5"})


def test_create_a_device_with_attributes(world, medical):
    api = world.api(world.manager)
    p = api.post("/products", SCREW, expected=201).json()
    assert p["attributes"] == {"ref": "71933215", "size": "4.5 x 30 mm", "sterile": True, "device_class": "IIb"}
    assert p["width"] is None and p["load_index"] is None
    assert p["size_display"] == "71933215 · 4.5 x 30 mm"
    assert p["display_name"] == "Orthex Cortical screw 71933215 · 4.5 x 30 mm"
    # Searchable by attribute value, like any other field.
    assert [x["sku"] for x in api.get("/products", params={"q": "71933215"}).json()] == ["MED-001"]
    assert [x["sku"] for x in api.get("/products", params={"q": "4.5 x 30"}).json()] == ["MED-001"]


def test_pack_rules_are_enforced(world, medical):
    api = world.api(world.manager)
    r = api.post("/products", {**SCREW, "attributes": {"size": "4.5 x 30 mm"}}, expected=422)
    assert "REF is required" in r.text
    r = api.post("/products", {**SCREW, "width": 205, "aspect_ratio": 55, "rim_diameter": 16}, expected=422)
    assert "Not used by the Medical devices and implants pack" in r.text


def test_update_replaces_the_attributes(world, medical):
    api = world.api(world.manager)
    pid = api.post("/products", SCREW, expected=201).json()["id"]
    p = api.patch(f"/products/{pid}", {"attributes": {"ref": "71933215", "size": "4.5 x 32 mm"}}).json()
    assert p["attributes"] == {"ref": "71933215", "size": "4.5 x 32 mm"}
    api.patch(f"/products/{pid}", {"attributes": {"size": "4.5 x 32 mm"}}, expected=422)


def test_tyres_still_require_a_size_and_reject_attributes(world):
    api = world.api(world.manager)
    tyre = {"sku": "T-NEW", "brand": "NORDWAY", "pattern": "ECOTRAIL", "width": 205, "aspect_ratio": 55,
            "rim_diameter": "16", "load_index": "91", "speed_rating": "h"}
    assert api.post("/products", tyre, expected=201).json()["display_name"] == "NORDWAY ECOTRAIL 205/55R16 91H"
    r = api.post("/products", {**tyre, "sku": "T-2", "width": None}, expected=422)
    assert "Required for a tyre: Width" in r.text
    api.post("/products", {**tyre, "sku": "T-3", "attributes": {"ref": "x"}}, expected=422)


def _upload(api, content: bytes, commit: bool):
    return api.post("/products/import", {"filename": "devices.xlsx", "commit": commit,
                                         "content_base64": base64.b64encode(content).decode()}).json()


def test_generic_template_import_and_export_round_trip(world, medical):
    api = world.api(world.warehouse_op)
    tpl = load_workbook(io.BytesIO(api.get("/products/import/template").content))
    headers = [c.value for c in tpl["SKUs"][1]]
    assert headers[:6] == ["SKU Code", "Device", "Manufacturer", "Description", "Barcode", "Active (Y/N)"]
    assert {"REF", "Size", "Class", "Sterile", "Tracking"} <= set(headers)

    wb = Workbook()
    ws = wb.active
    ws.append(["Device import"])                                   # title rows above the header are fine
    ws.append(["SKU Code", "Device", "Manufacturer", "REF", "Size", "Sterile", "Dealer price"])
    ws.append(["MED-100", "Locking plate", "Orthex", "88010", "6 hole", "Y", 950])
    ws.append(["MED-101", "Cortical screw", "Orthex", "71933215", "4.5 x 30 mm", "maybe", 12])
    ws.append(["MED-102", "Drill bit", "Orthex", "", "3.2 mm", "N", 40])
    buf = io.BytesIO()
    wb.save(buf)

    check = _upload(api, buf.getvalue(), commit=False)
    assert check["summary"] == {"create": 1, "update": 0, "unchanged": 0, "error": 2, "total": 3}
    assert check["notes"] == ["Price columns are ignored: prices are managed in the accounting system"]
    errors = {r["sku"]: r["errors"] for r in check["rows"] if r["errors"]}
    assert errors == {"MED-101": ["Sterile must be Yes or No"], "MED-102": ["REF is required"]}
    ok = next(r for r in check["rows"] if r["sku"] == "MED-100")
    assert ok["size"] == "88010 · 6 hole" and ok["attributes"] == {"ref": "88010", "size": "6 hole", "sterile": True}

    assert _upload(api, buf.getvalue(), commit=True)["result"] == {"created": 1, "updated": 0, "unchanged": 0,
                                                                    "skipped": 2}
    world.db.expire_all()
    plate = world.db.execute(select(Product).where(Product.sku == "MED-100")).scalar_one()
    assert (plate.pattern, plate.brand, plate.attributes["sterile"]) == ("Locking plate", "Orthex", True)
    assert world.db.execute(select(StockBalance)).first() is None        # an import never creates stock

    # Export → re-import is unchanged; editing an attribute is reported as an update.
    exported = api.get("/products/export").content
    again = _upload(api, exported, commit=False)
    assert again["summary"]["error"] == 3           # the three tyres in the test world can't be imported as devices
    assert next(r for r in again["rows"] if r["sku"] == "MED-100")["action"] == "unchanged"
    wb2 = load_workbook(io.BytesIO(exported))
    sheet = wb2["SKUs"]
    hdr = [c.value for c in sheet[1]]
    for row in sheet.iter_rows(min_row=2):
        if row[0].value == "MED-100":
            row[hdr.index("Size")].value = "8 hole"
    buf2 = io.BytesIO()
    wb2.save(buf2)
    edited = next(r for r in _upload(api, buf2.getvalue(), commit=False)["rows"] if r["sku"] == "MED-100")
    assert edited["action"] == "update" and edited["changes"] == ["Attributes: Size 6 hole → 8 hole"]


def test_public_config_describes_the_item_fields(client, medical):
    industry = client.get("/api/config/public").json()["industry"]
    assert (industry["brand_label"], industry["name_label"], industry["spec_label"]) == ("Manufacturer", "Device",
                                                                                         "Spec")
    assert industry["tyre_fields"] is False
    ref = next(a for a in industry["attributes"] if a["key"] == "ref")
    assert ref == {"key": "ref", "label": "REF", "type": "text", "required": True, "in_spec": True, "options": [],
                   "unit": "", "help": "Manufacturer catalogue number.", "example": "71933215", "column": False}


@pytest.mark.parametrize("pack,expected", [("medical", 6), ("auto_parts", 3), ("building", 3)])
def test_sample_catalogues_import_cleanly(world, monkeypatch, pack, expected):
    from pathlib import Path

    monkeypatch.setattr(get_settings(), "industry_pack", pack)
    path = Path(__file__).resolve().parents[1] / "data" / "products" / f"sample-{pack.replace('_', '-')}-catalogue.xlsx"
    check = _upload(world.api(world.warehouse_op), path.read_bytes(), commit=False)
    assert check["summary"] == {"create": expected, "update": 0, "unchanged": 0, "error": 0, "total": expected}
