"""Report by dealer, by SKU (finding 31): per shop and tyre, what the dealer holds, what is on its way, what is waiting,
and what was sold and invoiced in the period. Units only (no prices, D2). Read-only.

Sold = confirmed sale quantity (after reversals) with a sale date in the period. Invoiced = the part of that sold
quantity whose invoice record has been marked as invoiced in Xero; not yet invoiced = the rest (no record yet, or a
record still in draft). So sold = invoiced + not yet invoiced on every row.
"""

from collections import defaultdict
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.industry import vocab
from app.modules.catalogue.models import Product
from app.modules.customers.models import Location, LocationType, Reseller
from app.modules.inventory.models import StockBalance
from app.modules.replenishment.models import OPEN_STATUSES, ReplenishmentRequest
from app.modules.sales.models import ConsignmentSale, ConsignmentSaleLine, InvoiceStatus, SaleSource
from app.modules.transfers.models import Transfer, TransferStatus

METRICS = ("on_hand", "available", "held", "on_the_way", "waiting", "sold", "invoiced", "not_invoiced")
LABELS = {"on_hand": "On hand", "available": "Available", "held": "Held (reserved + blocked)",
          "on_the_way": "On the way", "waiting": "Waiting (awaiting supply)", "sold": "Sold in period",
          "invoiced": "Invoiced in Xero", "not_invoiced": "Not yet invoiced"}


def default_period(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today.replace(day=1), today


def dealer_sku(db: Session, *, reseller_id: int | None = None, location_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None) -> dict:
    start, end = default_period()
    date_from, date_to = date_from or start, date_to or end
    shops = select(Location.id).join(Reseller, Reseller.id == Location.reseller_id).where(
        Location.type == LocationType.CONSIGNMENT, Reseller.is_cash_account.is_(False))
    if reseller_id is not None:
        shops = shops.where(Location.reseller_id == reseller_id)
    if location_id is not None:
        shops = shops.where(Location.id == location_id)
    shop_ids = set(db.execute(shops).scalars())
    rows: dict[tuple[int, int], dict] = defaultdict(lambda: dict.fromkeys(METRICS, 0))
    if not shop_ids:
        return _shape(db, rows, date_from, date_to)

    for b in db.execute(select(StockBalance).where(StockBalance.location_id.in_(shop_ids))).scalars():
        if b.on_hand or b.reserved or b.blocked:
            r = rows[(b.location_id, b.product_id)]
            r["on_hand"], r["available"], r["held"] = b.on_hand, b.available, b.reserved + b.blocked
    for req in db.execute(select(ReplenishmentRequest).where(
            ReplenishmentRequest.location_id.in_(shop_ids),
            ReplenishmentRequest.status.in_([s.value for s in OPEN_STATUSES]))).scalars():
        if req.qty_in_transit or req.qty_awaiting_supply:
            r = rows[(req.location_id, req.product_id)]
            r["on_the_way"] += req.qty_in_transit
            r["waiting"] += req.qty_awaiting_supply
    for t in db.execute(select(Transfer).where(
            Transfer.destination_location_id.in_(shop_ids),
            Transfer.status.in_([TransferStatus.IN_TRANSIT.value, TransferStatus.RECEIVED_WITH_DISCREPANCY.value]))
            ).scalars():
        if t.qty_in_transit:
            rows[(t.destination_location_id, t.product_id)]["on_the_way"] += t.qty_in_transit
    sold = db.execute(
        select(ConsignmentSale.location_id, ConsignmentSaleLine)
        .join(ConsignmentSaleLine, ConsignmentSaleLine.sale_id == ConsignmentSale.id)
        .where(ConsignmentSale.location_id.in_(shop_ids), ConsignmentSale.source != SaleSource.CASH_SALE,
               ConsignmentSale.sale_date >= date_from, ConsignmentSale.sale_date <= date_to)
    ).tuples()
    for loc_id, ln in sold:
        qty = ln.chargeable_qty
        if qty <= 0:
            continue
        r = rows[(loc_id, ln.product_id)]
        r["sold"] += qty
        r["invoiced" if ln.invoice_status == InvoiceStatus.INVOICED else "not_invoiced"] += qty
    return _shape(db, rows, date_from, date_to)


def _shape(db: Session, rows: dict, date_from: date, date_to: date) -> dict:
    locs = {loc.id: loc for loc in db.execute(
        select(Location).where(Location.id.in_({k[0] for k in rows}))).scalars()} if rows else {}
    products = {p.id: p for p in db.execute(
        select(Product).where(Product.id.in_({k[1] for k in rows}))).scalars()} if rows else {}
    dealers = {r.id: r for r in db.execute(
        select(Reseller).where(Reseller.id.in_({loc.reseller_id for loc in locs.values()})))
        .scalars()} if locs else {}
    by_dealer: dict[int, dict] = {}
    for (loc_id, product_id), m in rows.items():
        if not any(m.values()):
            continue
        loc, p = locs[loc_id], products[product_id]
        d = dealers[loc.reseller_id]
        group = by_dealer.setdefault(d.id, {"reseller_id": d.id, "reseller_name": d.business_name,
                                            "account_ref": d.account_ref, "rows": [],
                                            "totals": dict.fromkeys(METRICS, 0)})
        group["rows"].append({"location_id": loc.id, "location_code": loc.code, "shop": loc.name, "city": loc.city,
                              "product_id": p.id, "sku": p.sku, "tyre": p.display_name, **m})
        for k in METRICS:
            group["totals"][k] += m[k]
    groups = sorted(by_dealer.values(), key=lambda g: g["reseller_name"].lower())
    for g in groups:
        g["rows"].sort(key=lambda r: (r["shop"].lower(), r["sku"]))
    totals = {k: sum(g["totals"][k] for g in groups) for k in METRICS}
    return {"date_from": date_from, "date_to": date_to, "dealers": groups, "totals": totals}


def to_xlsx(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"By {vocab.partner} by SKU"
    ws.append([f"Report by {vocab.partner}, by SKU — {report['date_from']:%d %b %Y} to {report['date_to']:%d %b %Y}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    header = [vocab.Partner, "Account ref", vocab.Site, "City", "SKU", vocab.Item, *[LABELS[k] for k in METRICS]]
    ws.append(header)
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F4F4F5")
    for g in report["dealers"]:
        for r in g["rows"]:
            ws.append([g["reseller_name"], g["account_ref"], r["shop"], r["city"], r["sku"], r["tyre"],
                       *[r[k] for k in METRICS]])
        ws.append([f"Total {g['reseller_name']}", g["account_ref"], "", "", "", "", *[g["totals"][k] for k in METRICS]])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
    ws.append([f"Total, all {vocab.partners}", "", "", "", "", "", *[report["totals"][k] for k in METRICS]])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for col, width in zip("ABCDEFGHIJKLMN", (28, 14, 22, 14, 16, 42, 10, 10, 14, 11, 14, 12, 14, 14), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A4"
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
