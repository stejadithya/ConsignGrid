"""Item attributes defined by the Industry Pack: validation, conversion and display.

Attribute values live in `products.attributes` (JSONB) as JSON scalars: text and choices as strings, integers and
numbers as numbers (numbers as strings with their decimals kept, never floats), booleans as true/false and dates as
ISO strings. The tyres pack's attributes are product columns and are validated by the product schema instead.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.industry import AttributeDef, IndustryPack

TRUE = {"y", "yes", "true", "1", "t"}
FALSE = {"n", "no", "false", "0", "f"}


class AttributeError_(ValueError):
    """One or more attribute values are not valid. The message lists every problem."""


def _convert(a: AttributeDef, value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
    if a.type == "text":
        text = str(value)
        if len(text) > 200:
            raise ValueError("is longer than 200 characters")
        return text
    if a.type == "integer":
        if isinstance(value, bool):
            raise ValueError("must be a whole number")
        try:
            d = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("must be a whole number") from exc
        if d != d.to_integral_value():
            raise ValueError("must be a whole number")
        return int(d)
    if a.type == "number":
        if isinstance(value, bool):
            raise ValueError("must be a number")
        try:
            d = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("must be a number") from exc
        if not d.is_finite():
            raise ValueError("must be a number")
        return str(d.normalize()) if d == d.to_integral_value() else str(d)
    if a.type == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).lower()
        if text in TRUE:
            return True
        if text in FALSE:
            return False
        raise ValueError("must be Yes or No")
    if a.type == "date":
        try:
            return (value if isinstance(value, date) else date.fromisoformat(str(value)[:10])).isoformat()
        except ValueError as exc:
            raise ValueError("must be a date (YYYY-MM-DD)") from exc
    if a.type == "choice":
        match = next((o for o in a.options if o.lower() == str(value).lower()), None)
        if match is None:
            raise ValueError(f"must be one of: {', '.join(a.options)}")
        return match
    raise ValueError(f"has an unknown type {a.type}")


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def clean_attributes(pack: IndustryPack, raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    """Validate and convert attribute values for `pack`. Blank values are dropped. Raises AttributeError_ listing every
    problem: unknown keys, missing required values (unless `partial`) and values of the wrong type."""
    raw = raw or {}
    defs = {a.key: a for a in pack.attributes if not a.column}
    problems: list[str] = []
    unknown = sorted(set(raw) - set(defs))
    if unknown:
        problems.append(f"Unknown attribute(s): {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for key, a in defs.items():
        value = raw.get(key)
        if is_blank(value):
            if a.required and not partial:
                problems.append(f"{a.label} is required")
            continue
        try:
            out[key] = _convert(a, value)
        except ValueError as exc:
            problems.append(f"{a.label} {exc}")
    if problems:
        raise AttributeError_("; ".join(problems))
    return out


def display_value(a: AttributeDef, value: Any) -> str:
    if value is None:
        return ""
    if a.type == "boolean":
        return a.label if value else ""
    text = str(value)
    return f"{text} {a.unit}".strip() if a.unit and a.type in ("integer", "number") else text


def spec_text(pack: IndustryPack, attributes: dict[str, Any] | None) -> str:
    """The short specification of a non-tyre item from its in-spec attributes, e.g. "71933215 · 4.5 x 30 mm"."""
    attributes = attributes or {}
    parts = [display_value(a, attributes.get(a.key)) for a in pack.attributes if a.in_spec and not a.column]
    return " · ".join(p for p in parts if p)
