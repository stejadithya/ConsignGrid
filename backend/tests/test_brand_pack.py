"""White-label Brand Pack: every customer-visible name comes from configuration, and the previous customer's brand
never appears in the product."""

import re
from pathlib import Path

from app.core.config import Settings, get_settings

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
OLD_BRAND = re.compile(r"tyre\s?grow", re.IGNORECASE)


def test_names_follow_the_product_name_unless_set():
    s = Settings(app_display_name="StockLoop")
    assert (s.company_name, s.invoice_issuer_name, s.file_prefix) == ("StockLoop", "StockLoop", "StockLoop")
    s = Settings(app_display_name="StockLoop", company_name="Acme Tyres Ltd")
    assert (s.company_name, s.invoice_issuer_name, s.file_prefix) == ("Acme Tyres Ltd", "Acme Tyres Ltd", "Acme-Tyres-Ltd")
    s = Settings(company_name="Acme Tyres Ltd", invoice_issuer_name="Acme Tyres Holdings Limited")
    assert s.invoice_issuer_name == "Acme Tyres Holdings Limited"


def test_the_api_reports_the_configured_brand(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_display_name", "StockLoop")
    assert client.get("/api/health").json()["name"] == "StockLoop"


def test_brand_name_drives_download_file_names(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "company_name", "Acme Tyres Ltd")
    r = world.api(world.manager).get("/products/import/template")
    assert 'filename="Acme-Tyres-Ltd_SKU_Import_Template.xlsx"' in r.headers["content-disposition"]


def test_previous_customer_brand_is_not_in_the_product():
    """The handover pack must not ship the previous customer's name in code, assets or configuration."""
    roots = [APP_ROOT / "app", APP_ROOT / "scripts", REPO_ROOT / "frontend" / "src", REPO_ROOT / "frontend" / "public"]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            if OLD_BRAND.search(path.name):
                offenders.append(str(path))
                continue
            text_file = path.suffix in {".py", ".ts", ".tsx", ".css", ".svg", ".json", ".md"}
            if text_file and OLD_BRAND.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(path))
    assert offenders == []
