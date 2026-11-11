"""Accounting integration boundary.

The MVP keeps its own invoice records. To integrate with an accounting platform, implement
`AccountingExporter.export()` for that platform and register it in `get_exporter()`; the invoice
payload below is the stable contract. Nothing in the rest of the system depends on the platform.
"""

from typing import Any, Protocol

from app.modules.invoicing.models import Invoice


class AccountingExporter(Protocol):
    name: str

    def export(self, payload: dict[str, Any]) -> str | None:
        """Send the invoice; return the external document id if the platform assigns one."""


class ManualExporter:
    """Default: no live integration. The payload is downloaded and keyed in / imported manually."""

    name = "manual"

    def export(self, payload: dict[str, Any]) -> str | None:
        return None


def get_exporter() -> AccountingExporter:
    return ManualExporter()


def invoice_payload(inv: Invoice) -> dict[str, Any]:
    return {
        "schema": "invoice.v1",
        "number": inv.number,
        "status": inv.status.value,
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat(),
        "currency": inv.currency,
        "customer": {
            "account_ref": inv.bill_to_account_ref,
            "name": inv.bill_to_name,
            "address": inv.bill_to_address,
            "tax_number": inv.bill_to_tax_number,
        },
        "lines": [
            {
                "sku": ln.sku,
                "description": ln.description,
                "quantity": ln.quantity,
                "unit_price": str(ln.unit_price),
                "tax_code": ln.tax_code,
                "tax_rate": str(ln.tax_rate),
                "net": str(ln.line_net),
                "tax": str(ln.line_tax),
                "total": str(ln.line_total),
                "source": {"sale_number": ln.sale_number, "sale_date": ln.sale_date.isoformat(),
                           "location": ln.location_code},
            }
            for ln in inv.lines if ln.is_active or inv.status.value == "VOID"
        ],
        "subtotal": str(inv.subtotal),
        "tax_total": str(inv.tax_total),
        "total": str(inv.total),
        "external_reference": inv.external_reference,
    }
