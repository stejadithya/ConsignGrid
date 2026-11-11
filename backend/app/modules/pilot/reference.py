"""Reference documents shown in the app (e.g. a supplier or dealer price list).

Documents are served through the authenticated API, never as public static files, because they can be
commercially confidential. They are reference material only: nothing here creates products or stock.

White-label: each customer deployment supplies its own documents. Put the files and a `manifest.json` in the
directory named by the `REFERENCE_DOCUMENTS_DIR` setting (default: `app/assets/reference`, which ships empty).
`manifest.json` is a list of objects with the fields of `ReferenceDocument`, e.g.

    [{"id": "price-list-2026-07", "title": "Dealer Price List", "description": "Prices in NZD. Confidential.",
      "effective_date": "2026-07-07", "filename": "price-list.jpg", "media_type": "image/jpeg",
      "width": 1455, "height": 2000}]
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.config import get_settings

DEFAULT_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "reference"


@dataclass(frozen=True)
class ReferenceDocument:
    id: str
    title: str
    description: str
    effective_date: date
    filename: str
    media_type: str
    width: int
    height: int


def asset_dir() -> Path:
    configured = get_settings().reference_documents_dir
    return Path(configured) if configured else DEFAULT_ASSET_DIR


def list_documents() -> tuple[ReferenceDocument, ...]:
    manifest = asset_dir() / "manifest.json"
    if not manifest.is_file():
        return ()
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    return tuple(ReferenceDocument(**{**r, "effective_date": date.fromisoformat(r["effective_date"])}) for r in rows)


def get_document(doc_id: str) -> ReferenceDocument | None:
    return next((d for d in list_documents() if d.id == doc_id), None)
