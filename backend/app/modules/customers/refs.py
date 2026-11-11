"""Automatic dealer account references (decision D4): DDD-CCC-NNN, e.g. AKT-AUC-001.

DDD  three letters from the business name: the first word's initial, then (if there are fewer than three words)
     the first word's next letters, then the initials of the following words. Ltd, Limited, Co, Company, The,
     And, & and NZ are ignored. "Akash Kumar Tyres" → AKT, "Tyre World Ltd" → TYW, "Bridgestone" → BRI.
CCC  the first three letters of the first shop's city: Auckland → AUC, Wellington → WEL.
NNN  the next free number for that prefix: 001, 002 … (four digits after 999).

Numbers come from a locked number_sequences row (e.g. "AKTAUC"), never lower than the highest reference already
in use, so a cleared sequence can never hand out a reference that exists. Existing references never change.
"""

import re

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.customers.models import Reseller

IGNORED = {"LTD", "LIMITED", "CO", "COMPANY", "THE", "AND", "NZ"}


def _letters(s: str) -> str:
    return re.sub(r"[^A-Z]", "", s.upper())


def dealer_code(business_name: str) -> str:
    words = [w for w in (_letters(t) for t in re.split(r"[\s&]+", business_name or "")) if w and w not in IGNORED]
    if not words:
        return "XXX"
    first, rest = words[0], words[1:3]
    extra = first[1:1 + 3 - 1 - len(rest)]
    return (first[0] + extra + "".join(w[0] for w in rest)).ljust(3, "X")[:3]


def city_code(city: str | None) -> str:
    return _letters(city or "")[:3].ljust(3, "X")


def _prefix(business_name: str, city: str | None) -> tuple[str, str]:
    d, c = dealer_code(business_name), city_code(city)
    return f"{d}-{c}-", f"{d}{c}"


def _highest_in_use(db: Session, ref_prefix: str) -> int:
    best = 0
    for ref in db.execute(select(Reseller.account_ref).where(Reseller.account_ref.like(f"{ref_prefix}%"))).scalars():
        tail = ref[len(ref_prefix):]
        if tail.isdigit():
            best = max(best, int(tail))
    return best


def _format(ref_prefix: str, n: int) -> str:
    return f"{ref_prefix}{n:03d}"


def preview(db: Session, business_name: str, city: str | None) -> str:
    """The reference the next dealer would get, without reserving it."""
    ref_prefix, seq = _prefix(business_name, city)
    current = db.execute(text("SELECT next_value FROM number_sequences WHERE prefix = :p"), {"p": seq}).scalar()
    return _format(ref_prefix, max(current or 1, _highest_in_use(db, ref_prefix) + 1))


def next_account_ref(db: Session, business_name: str, city: str | None) -> str:
    """Reserve the next reference for this name and city (serialised per prefix by the row lock)."""
    ref_prefix, seq = _prefix(business_name, city)
    db.execute(text("INSERT INTO number_sequences (prefix, next_value) VALUES (:p, 1) ON CONFLICT (prefix) DO NOTHING"),
               {"p": seq})
    current = db.execute(text("SELECT next_value FROM number_sequences WHERE prefix = :p FOR UPDATE"), {"p": seq}).scalar_one()
    n = max(current, _highest_in_use(db, ref_prefix) + 1)
    db.execute(text("UPDATE number_sequences SET next_value = :n WHERE prefix = :p"), {"n": n + 1, "p": seq})
    return _format(ref_prefix, n)
