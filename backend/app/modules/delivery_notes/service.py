"""Delivery notes: a standard PDF and email telling a reseller what was delivered and when.

The PDF can always be downloaded. Emails are sent only when SMTP is configured (SMTP_HOST etc.); until then the
attempt is recorded as "not configured" and nothing leaves the system. Sending never blocks or undoes a receipt.
"""

import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, Reseller
from app.modules.identity.models import User
from app.modules.proofs.service import first_photo
from app.modules.replenishment.models import Delivery
from app.modules.transfers.models import Transfer


class DeliveryNoteError(Exception):
    pass


def _local(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo(get_settings().business_timezone))


def note_data(db: Session, delivery: Delivery) -> dict:
    """Everything the PDF and the email show, in one place (one standard format)."""
    settings = get_settings()
    reseller = db.get(Reseller, delivery.reseller_id)
    loc = db.get(Location, delivery.to_location_id)
    received = _local(delivery.received_at) if delivery.received_at else None
    lines = []
    for ln in delivery.lines:
        p = db.get(Product, ln.product_id)
        lines.append({"tyre": p.display_name if p else "", "sku": p.sku if p else "", "shipped": ln.qty_dispatched,
                      "delivered": ln.qty_received + ln.qty_late_received})
    carried = db.get(User, delivery.carried_by_user_id) if delivery.carried_by_user_id else None
    return {
        "company": settings.invoice_issuer_name, "company_details": settings.invoice_issuer_details,
        "number": delivery.number, "reseller": reseller.business_name, "account_ref": reseller.account_ref,
        "contact": reseller.contact_name, "email": reseller.email, "location": f"{loc.code} — {loc.name}",
        "address": delivery.shipping_address or "",
        "delivered_date": (delivery.delivered_on.strftime("%d %B %Y") if delivery.delivered_on
                           else received.strftime("%d %B %Y") if received else "Not yet delivered"),
        "delivered_time": received.strftime("%I:%M %p").lstrip("0") if received else "",
        "timezone": settings.business_timezone, "reference": delivery.delivery_reference or "",
        "method": "Sales representative" + (f" ({carried.full_name})" if carried else "")
        if delivery.shipping_method == "SALES_REP" else f"Courier: {delivery.carrier_reference or '—'}",
        "tracking": delivery.tracking_number or "", "lines": lines,
        "total_delivered": sum(ln["delivered"] for ln in lines), "total_shipped": sum(ln["shipped"] for ln in lines),
        "discrepancy_days": settings.delivery_discrepancy_days,
        "received_by": delivery.received_by_name or "", "receipt_notes": delivery.receipt_notes or "",
        "photo": first_photo(db, "delivery", delivery.id),
    }


def note_data_for_transfer(db: Session, t: Transfer) -> dict:
    """The same standard note for a transfer between dealers: addressed to the destination, which tyres, no prices.
    The source dealer is never named (dealers do not see each other)."""
    settings = get_settings()
    reseller = db.get(Reseller, t.destination_reseller_id)
    loc = db.get(Location, t.destination_location_id)
    received = _local(t.received_at) if t.received_at else None
    p = db.get(Product, t.product_id)
    lines = [{"tyre": p.display_name if p else "", "sku": p.sku if p else "", "shipped": t.qty_collected or t.quantity,
              "delivered": t.qty_received}]
    carried = db.get(User, t.carried_by_user_id) if t.carried_by_user_id else None
    parts = [loc.address_line1, loc.address_line2, loc.city, loc.region, loc.postcode, loc.country]
    return {
        "company": settings.invoice_issuer_name, "company_details": settings.invoice_issuer_details,
        "number": t.number, "reseller": reseller.business_name, "account_ref": reseller.account_ref,
        "contact": reseller.contact_name, "email": reseller.email, "location": f"{loc.code} — {loc.name}",
        "address": ", ".join(x for x in parts if x),
        "delivered_date": received.strftime("%d %B %Y") if received else "Not yet delivered",
        "delivered_time": received.strftime("%I:%M %p").lstrip("0") if received else "",
        "timezone": settings.business_timezone, "reference": "",
        "method": ("Sales representative" + (f" ({carried.full_name})" if carried else "")
                   if t.shipping_method == "SALES_REP" else f"Courier: {t.carrier_reference or '—'}"
                   if t.shipping_method == "COURIER" else "Transfer between dealers"),
        "tracking": t.tracking_number or "", "lines": lines,
        "total_delivered": sum(ln["delivered"] for ln in lines), "total_shipped": sum(ln["shipped"] for ln in lines),
        "discrepancy_days": settings.delivery_discrepancy_days,
        "received_by": t.received_by_name or "", "receipt_notes": t.receipt_notes or "",
        "photo": first_photo(db, "transfer", t.id),
    }


def _txt(s: object) -> str:
    """Core PDF fonts are Latin-1: replace characters they cannot draw."""
    return str(s).replace("—", "-").replace("–", "-").replace("×", "x").encode("latin-1", "replace").decode("latin-1")


def render_pdf(data: dict) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, _txt(data["company"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if data["company_details"]:
        pdf.multi_cell(0, 4.5, _txt(data["company_details"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _txt(f"Delivery note {data['number']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    rows = [("Delivered to", f"{data['reseller']} ({data['account_ref']})"), ("Location", data["location"]),
            ("Address", data["address"] or "-"),
            ("Delivered on", f"{data['delivered_date']}{' at ' + data['delivered_time'] if data['delivered_time'] else ''}"),
            ("Shipped by", data["method"])]
    if data["tracking"]:
        rows.append(("Tracking number", data["tracking"]))
    if data["reference"]:
        rows.append(("Delivery reference", data["reference"]))
    if data.get("received_by"):
        rows.append(("Received by", data["received_by"]))
    if data.get("receipt_notes"):
        rows.append(("Hand-over notes", data["receipt_notes"]))
    for k, v in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(42, 6, _txt(k))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _txt(v), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    widths = (100, 34, 23, 23)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 10)
    for w, h in zip(widths, ("Tyre", "SKU", "Shipped", "Delivered"), strict=True):
        pdf.cell(w, 8, h, border=1, fill=True, align="R" if h in ("Shipped", "Delivered") else "L")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for ln in data["lines"]:
        pdf.cell(widths[0], 7, _txt(ln["tyre"])[:60], border=1)
        pdf.cell(widths[1], 7, _txt(ln["sku"]), border=1)
        pdf.cell(widths[2], 7, str(ln["shipped"]), border=1, align="R")
        pdf.cell(widths[3], 7, str(ln["delivered"]), border=1, align="R")
        pdf.ln()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(widths[0] + widths[1], 8, "Total tyres", border=1)
    pdf.cell(widths[2], 8, str(data["total_shipped"]), border=1, align="R")
    pdf.cell(widths[3], 8, str(data["total_delivered"]), border=1, align="R")
    pdf.ln(14)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5.5, _txt(
        f"If you notice any discrepancy with this delivery (quantity, size or condition), please contact us within "
        f"{data['discrepancy_days']} days of the delivery date."),
        new_x="LMARGIN", new_y="NEXT")
    if data.get("photo"):
        try:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, "Photo at drop-off", new_x="LMARGIN", new_y="NEXT")
            pdf.image(BytesIO(data["photo"]), w=70)
        except Exception:  # noqa: BLE001 - a photo problem must never block the delivery note
            pass
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _txt(f"Times shown in {data['timezone']}. Generated {_local(datetime.now(UTC)):%d %b %Y %H:%M}."))
    return bytes(pdf.output())


def render_email(data: dict) -> tuple[str, str, str]:
    """(subject, plain text, HTML) for the standard delivery email."""
    when = f"{data['delivered_date']}{' at ' + data['delivered_time'] if data['delivered_time'] else ''}"
    subject = (f"{data['company']} delivery {data['number']}: {data['total_delivered']} tyre(s) delivered on "
               f"{data['delivered_date']}")
    greeting = f"Dear {data['contact'] or data['reseller']},"
    rows_txt = "\n".join(f"  - {ln['delivered']} x {ln['tyre']} (SKU {ln['sku']})" for ln in data["lines"])
    closing = (f"If you notice any discrepancy with this delivery, please contact us within {data['discrepancy_days']} "
               "days of the delivery date.")
    text = (f"{greeting}\n\nThe following tyres were delivered to {data['reseller']} ({data['location']}) on {when}.\n\n"
            f"{rows_txt}\n\nTotal delivered: {data['total_delivered']} tyre(s)\nShipped by: {data['method']}\n"
            + (f"Received by: {data['received_by']}\n" if data.get("received_by") else "")
            + (f"Tracking number: {data['tracking']}\n" if data["tracking"] else "")
            + f"\n{closing}\n\nThe delivery note is attached as a PDF.\n\nKind regards,\n{data['company']}\n")
    e = {k: escape(str(v)) if isinstance(v, str) else v for k, v in data.items()}
    received_html = f"<br>Received by: {e['received_by']}" if e.get("received_by") else ""
    rows_html = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e4e4e7'>{escape(ln['tyre'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e4e4e7;font-family:monospace'>{escape(ln['sku'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e4e4e7;text-align:right'>{ln['delivered']}</td></tr>"
        for ln in data["lines"])
    html = f"""<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#18181b;max-width:640px">
<p>{escape(greeting)}</p>
<p>The following tyres were delivered to <b>{e['reseller']}</b> ({e['location']}) on <b>{escape(when)}</b>.</p>
<table style="border-collapse:collapse;width:100%;margin:12px 0">
<tr style="background:#f4f4f5"><th style="padding:6px 10px;text-align:left">Tyre</th>
<th style="padding:6px 10px;text-align:left">SKU</th>
<th style="padding:6px 10px;text-align:right">Delivered</th></tr>{rows_html}
<tr><td colspan="2" style="padding:6px 10px;font-weight:bold">Total delivered</td>
<td style="padding:6px 10px;text-align:right;font-weight:bold">{data['total_delivered']}</td></tr></table>
<p>Shipped by: {e['method']}{'<br>Tracking number: ' + e['tracking'] if e['tracking'] else ''}{received_html}</p>
<p style="background:#fffbe6;border:1px solid #facc15;padding:10px;border-radius:6px">{escape(closing)}</p>
<p>The delivery note is attached as a PDF.</p><p>Kind regards,<br>{e['company']}</p></div>"""
    return subject, text, html


def send_after_receipt(db: Session, delivery_id: int) -> None:
    """Automatic email once a delivery is confirmed. Runs after the receipt is committed and never raises."""
    try:
        delivery = db.get(Delivery, delivery_id)
        if delivery is not None and delivery.received_at is not None and delivery.note_emailed_at is None:
            send(db, delivery)
            db.commit()
    except Exception:  # noqa: BLE001 — an email problem must never affect the confirmed delivery
        db.rollback()


def send_after_transfer_receipt(db: Session, transfer_id: int) -> None:
    """Automatic email once a transfer is received at the destination. Never raises."""
    try:
        t = db.get(Transfer, transfer_id)
        if t is not None and t.received_at is not None and t.note_emailed_at is None:
            send_for_transfer(db, t)
            db.commit()
    except Exception:  # noqa: BLE001 — an email problem must never affect the confirmed transfer
        db.rollback()


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


def send(db: Session, delivery: Delivery) -> str:
    """Email the delivery note to the reseller. Records the outcome on the delivery; returns a short status."""
    return _send(delivery, note_data(db, delivery))


def send_for_transfer(db: Session, t: Transfer) -> str:
    """Email the transfer's delivery note to the destination dealer; same rules as deliveries."""
    return _send(t, note_data_for_transfer(db, t))


def _send(record: Delivery | Transfer, data: dict) -> str:
    """Send one note and record the outcome on the record's note_email_* fields."""
    delivery = record
    now = datetime.now(UTC)
    to = (data["email"] or "").strip()
    if not to:
        delivery.note_email_error = "The dealer has no email address"
        return "no_email"
    if not email_configured():
        delivery.note_email_error = "Email sending is not set up yet (SMTP settings); download the PDF instead"
        return "not_configured"
    s = get_settings()
    subject, text, html = render_email(data)
    msg = EmailMessage()
    msg["Subject"] = subject
    name, addr = parseaddr(s.smtp_from)
    msg["From"] = formataddr((name or data["company"], addr))
    msg["To"] = to
    if s.delivery_note_reply_to:
        msg["Reply-To"] = s.delivery_note_reply_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    msg.add_attachment(render_pdf(data), maintype="application", subtype="pdf",
                       filename=f"Delivery-note-{data['number']}.pdf")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        delivery.note_email_error = f"Sending failed: {type(exc).__name__}"
        return "failed"
    delivery.note_emailed_at, delivery.note_email_to, delivery.note_email_error = now, to, None
    return "sent"
