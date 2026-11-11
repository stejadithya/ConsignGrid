"""Product search the way people type it: sizes with or without the slash, several words, part of a SKU."""

import pytest


def skus(world, q):
    return sorted(p["sku"] for p in world.api(world.manager).get("/products", params={"q": q}).json())


@pytest.mark.parametrize(("q", "expected"), [
    ("205/55", ["TYR-001", "TYR-003"]),
    ("205 55", ["TYR-001", "TYR-003"]),
    ("20555", ["TYR-001", "TYR-003"]),
    ("205-55", ["TYR-001", "TYR-003"]),
    ("225/45R17", ["TYR-002"]),
    ("225 45 17", ["TYR-002"]),
    ("205 55 conti", ["TYR-003"]),
    ("Primacy", ["TYR-001"]),
    ("tyr 002", ["TYR-002"]),
    ("94w", ["TYR-002"]),
    ("195 65", []),
])
def test_search_ignores_spaces_and_punctuation_and_includes_the_size(world, q, expected):
    assert skus(world, q) == expected


def test_every_word_must_match_and_an_empty_search_lists_all(world):
    assert skus(world, "michelin 225") == []
    assert skus(world, "") == ["TYR-001", "TYR-002", "TYR-003"]
    assert skus(world, "   ") == ["TYR-001", "TYR-002", "TYR-003"]
