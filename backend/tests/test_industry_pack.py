"""Industry Packs: the same platform speaks each industry's language; the tyres pack keeps today's wording."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.industry import PACKS, TERM_KEYS, vocab


@pytest.fixture
def pack(monkeypatch):
    def use(code: str, **overrides: str):
        monkeypatch.setattr(get_settings(), "industry_pack", code)
        monkeypatch.setattr(get_settings(), "terms_overrides", overrides)
    return use


def test_tyres_is_the_default_and_keeps_the_original_words():
    assert Settings().industry_pack == "tyres"
    assert vocab.as_dict() == {"item": "tyre", "items": "tyres", "partner": "dealer", "partners": "dealers",
                               "site": "shop", "sites": "shops"}
    assert (vocab.Item, vocab.Partners, vocab.aPartner, vocab.ASite) == ("Tyre", "Dealers", "a dealer", "A shop")


def test_every_pack_defines_every_word():
    for p in PACKS.values():
        assert set(p.terms) == set(TERM_KEYS) and all(p.terms.values()), p.code


def test_articles_follow_the_word(pack):
    pack("generic")
    assert (vocab.aItem, vocab.AItem, vocab.aPartner) == ("an item", "An item", "a partner")


def test_a_customer_can_rename_single_words(pack):
    pack("tyres", partner="stockist", partners="stockists", unknown="ignored")
    assert (vocab.partner, vocab.Partners, vocab.item) == ("stockist", "Stockists", "tyre")


def test_unknown_pack_is_rejected():
    with pytest.raises(ValidationError):
        Settings(industry_pack="spaceships")


def test_messages_follow_the_pack(world, pack):
    pack("medical")
    r = world.api(world.manager).get("/resellers/999999", expected=404)
    assert r.json()["detail"] == "Hospital not found"


def test_public_config_needs_no_sign_in(client, pack):
    pack("auto_parts")
    body = client.get("/api/config/public").json()
    assert body["industry"]["code"] == "auto_parts"
    assert body["terms"]["sites"] == "branches"
    assert body["brand"]["product_name"] == get_settings().app_display_name
    assert {p["code"] for p in client.get("/api/config/industry-packs").json()} >= {"tyres", "generic", "medical"}
