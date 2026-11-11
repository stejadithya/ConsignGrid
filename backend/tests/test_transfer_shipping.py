"""Release 1.11 — a transfer between dealers is carried by a sales rep or a courier (finding 23): arrange the pick-up,
the rep collects and delivers, only the rep or the destination dealer confirms, a delivery note without prices."""

import re

import pytest

from app.core.permissions import Role
from app.modules.delivery_notes import service as delivery_notes
from app.modules.invoicing.models import Invoice
from app.modules.transfers.models import Transfer
from tests.factories import HANDOVER, make_user, set_stock

pytestmark = pytest.mark.usefixtures("ledger_balanced")   # every test ends with the ledger reconciled


def _approved(world, shipping=None):
    set_stock(world.db, world.loc_a, world.p3, 6)
    world.reseller_b.email = "owner@bravo.example.com"   # the delivery note goes to the destination dealer
    world.db.commit()
    mgr = world.api(world.manager)
    t = mgr.post("/transfers", {"destination_location_id": world.loc_b.id, "product_id": world.p3.id, "quantity": 2,
                                "reason": "Customer waiting"}, expected=201).json()
    body = {"source_location_id": world.loc_a.id, "source_consent_reference": "Phoned owner"}
    if shipping is not None:
        body["shipping"] = shipping
    return mgr.post(f"/transfers/{t['id']}/approve", body).json()


def _titles(world, user):
    return {n["title"]: n["body"] for n in world.api(user).get("/notifications").json()}


def test_rep_assigned_collects_and_only_rep_or_destination_dealer_confirms(world):
    t = _approved(world)
    wm, rep = world.api(world.warehouse_op), world.api(world.rep)
    url = f"/transfers/{t['id']}"
    wm.post(f"{url}/shipping", {"shipping_method": "SALES_REP"}, expected=422)                       # which rep?
    wm.post(f"{url}/shipping", {"shipping_method": "SALES_REP", "carried_by_user_id": world.manager.id}, expected=422)
    world.api(world.rep).post(f"{url}/shipping", {"shipping_method": "COURIER", "carrier_reference": "X"}, expected=403)
    t = wm.post(f"{url}/shipping", {"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id}).json()
    assert (t["shipping_method"], t["carried_by"], t["shipping_arranged_by"]) == ("SALES_REP", "Riley Rep", "Wes Warehouse")
    # The rep is told where to collect from and where to deliver.
    body = _titles(world, world.rep)[f"Please collect {t['number']} (2 × {world.p3.tyre_label})"]
    assert body.startswith("Collect from Alpha Tyres,") and " and deliver to Bravo Auto," in body

    # Other staff cannot record the collection; the rep must say who handed it over.
    wm.post(f"{url}/collect", {}, expected=403)
    rep.post(f"{url}/collect", {}, expected=422)
    t = rep.post(f"{url}/collect", {"collected_from_name": "Sam at Alpha"}).json()
    assert t["status"] == "IN_TRANSIT" and t["collected_from_name"] == "Sam at Alpha"
    # The destination dealer hears it is on its way; the source dealer that the replacement was raised.
    assert _titles(world, world.user_b)["Tyres are on their way to you"] == f"2 × {world.p3.tyre_label} ({t['number']})"
    assert f"Collected; your replacement has been raised ({t['source_request']['number']})" in _titles(world, world.user_a)
    # The destination dealer does not see who handed it over at the other dealer.
    assert world.api(world.user_b).get(url).json()["collected_from_name"] is None

    # Only the rep or the destination dealer confirms.
    other_rep = make_user(world.db, Role.SALES_REP, "other.rep@example.com")
    world.db.commit()
    wm.post(f"{url}/receive", HANDOVER, expected=403)
    world.api(world.manager).post(f"{url}/receive", HANDOVER, expected=403)
    world.api(other_rep).post(f"{url}/receive", HANDOVER, expected=403)
    world.api(world.user_a).post(f"{url}/receive", {}, expected=404)        # the source dealer
    t = rep.post(f"{url}/receive", HANDOVER).json()
    assert t["status"] == "COMPLETED" and t["received_by_name"] == "Shop owner"
    assert "not set up" in t["note_email_error"]                              # emailed under the usual SMTP rules
    assert world.bal(world.loc_b, world.p3).on_hand == 2
    assert wm.get("/inventory/reconciliation").json()["balanced"] is True


def test_delivery_note_lists_tyres_and_quantities_without_prices(world):
    t = _approved(world, shipping={"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id})
    rep = world.api(world.rep)
    rep.post(f"/transfers/{t['id']}/collect", {"collected_from_name": "Sam"})
    rep.post(f"/transfers/{t['id']}/receive", HANDOVER)
    data = delivery_notes.note_data_for_transfer(world.db, world.db.get(Transfer, t["id"]))
    assert data["lines"] == [{"tyre": world.p3.display_name, "sku": "TYR-003", "shipped": 2, "delivered": 2}]
    assert data["reseller"] == "Bravo Auto" and data["method"] == "Sales representative (Riley Rep)"
    subject, text, html = delivery_notes.render_email(data)
    for part in (subject, text, html, str(data)):
        assert not re.search(r"\$\s?\d|price|195\.00|130\.00", part, re.I)
        assert "Alpha" not in part                                           # the source dealer is never named
    pdf = world.api(world.user_b).get(f"/transfers/{t['id']}/delivery-note.pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
    world.api(world.warehouse_op).get(f"/transfers/{t['id']}/delivery-note.pdf", expected=200)
    world.api(world.user_a).get(f"/transfers/{t['id']}/delivery-note.pdf", expected=404)   # source dealer
    out = world.api(world.warehouse_op).post(f"/transfers/{t['id']}/email-delivery-note").json()
    assert out["status"] == "not_configured"


def test_source_replacement_is_raised_and_no_invoice_is_created(world):
    t = _approved(world, shipping={"shipping_method": "SALES_REP", "carried_by_user_id": world.rep.id})
    invoices_before = world.db.query(Invoice).count()
    t = world.api(world.rep).post(f"/transfers/{t['id']}/collect", {"collected_from_name": "Sam"}).json()
    req = world.api(world.warehouse_op).get(f"/replenishment/requests/{t['source_request']['id']}").json()
    assert (req["reason"], req["qty_required"], req["location_id"]) == ("TRANSFER", 2, world.loc_a.id)
    world.api(world.rep).post(f"/transfers/{t['id']}/receive", HANDOVER)
    assert world.db.query(Invoice).count() == invoices_before


def test_courier_path(world):
    t = _approved(world)
    wm = world.api(world.warehouse_op)
    url = f"/transfers/{t['id']}"
    wm.post(f"{url}/shipping", {"shipping_method": "COURIER"}, expected=422)                         # which courier?
    t = wm.post(f"{url}/shipping", {"shipping_method": "COURIER", "carrier_reference": "FastFreight",
                                    "tracking_number": "FF123"}).json()
    assert (t["shipping_method"], t["carrier_reference"], t["tracking_number"], t["carried_by"]) == \
        ("COURIER", "FastFreight", "FF123", None)
    t = wm.post(f"{url}/collect", {}).json()                                  # no rep: warehouse staff record it
    assert t["status"] == "IN_TRANSIT"
    wm.post(f"{url}/shipping", {"shipping_method": "COURIER", "carrier_reference": "X"}, expected=409)  # too late
    t = world.api(world.user_b).post(f"{url}/receive", {}).json()
    assert t["status"] == "COMPLETED"


def test_older_transfers_without_shipping_keep_todays_rules(world):
    t = _approved(world)
    t = world.api(world.warehouse_op).post(f"/transfers/{t['id']}/collect", {}).json()
    assert t["shipping_method"] is None
    t = world.api(world.warehouse_op).post(f"/transfers/{t['id']}/receive", {"received_by_name": "Mia"}).json()
    assert t["status"] == "COMPLETED"
