"use client";

import Link from "next/link";
import { ArrowLeftRight, ClipboardCheck, MapPin, PackagePlus, RefreshCw, ShoppingCart, Truck } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CheckStockButton } from "@/components/CheckStock";
import { StockCheckSchedule } from "@/components/StockCheckSchedule";
import { invalidateReference, ProductSelect, ShopLabel, shopText } from "@/components/pickers";
import { AgreementFilesCard } from "@/components/AgreementFiles";
import { InitialStockModal } from "@/components/InitialStock";
import { DealerHistoryTab } from "@/components/DealerHistory";
import { ResellerHistory } from "@/components/ResellerHistory";
import { RequestsTable, TransfersTable } from "@/components/tables";
import { links, NumLink } from "@/components/NumLink";
import { StockOrigin } from "@/components/StockOrigin";
import {
  Alert, Badge, Button, ButtonLink, Card, ConfirmDialog, cx, DataTable, DefinitionList, Field, Input, Loading,
  MetricStrip, Modal, MoreMenu, PageHeader, ProductCell, Qty, Select, Tabs,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, humanize } from "@/lib/format";
import { saleSourceLabel } from "@/lib/saleJourney";
import { useAction, useApi } from "@/lib/hooks";
import type {
  AllocationPosition, Delivery, Invoice, ReplenishmentRequest, Reseller, Sale, Stocktake, Transfer,
} from "@/lib/types";

export default function ResellerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const rid = Number(id);
  const { can, user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [initialOpen, setInitialOpen] = useState(false);
  const { data: r, error, reload } = useApi<Reseller>(`/resellers/${rid}`);
  const staff = !user?.reseller_id;

  if (error) return <Alert>{error}</Alert>;
  if (!r) return <Loading />;

  return (
    <>
      <PageHeader eyebrow={staff ? "Dealer account" : "My account"}
        title={<span className="flex flex-wrap items-center gap-3">
          <span aria-hidden className="inline-flex size-10 items-center justify-center rounded-card bg-brand text-subheading font-semibold text-ink">
            {r.business_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
          </span>
          {r.business_name} <Badge value={r.status} />
          {staff && missingDetails(r).length > 0 && <span title={`Missing: ${missingDetails(r).join(", ")}`}><Badge value="ACTION_REQUIRED" label="Missing details" /></span>}</span>}
        meta={<><span>Account <span className="sku text-ink">{r.account_ref}</span></span>
          <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{r.locations.length} location(s){r.locations[0]?.city ? ` · ${r.locations[0].city}` : ""}</span>
          <span>Sales rep <span className="text-ink">{r.sales_rep_name ?? "unassigned"}</span></span>
          {r.payment_terms_days !== null && <span>Terms <span className="text-ink">{r.payment_terms_days} days</span></span>}</>}
        mobileActions={staff ? <>
          {can("transfer.request") && <CheckStockButton />}
          <MoreMenu items={[
            can("reseller.initial_stock") && r.joined_with_stock !== false && { label: "Initial stock", icon: PackagePlus, onSelect: () => setInitialOpen(true) },
            can("stock_request.create") && r.joined_with_stock === false && { label: "Order stock", icon: PackagePlus, href: `/stock-requests/new?location=${r.locations[0]?.id ?? ""}` },
            can("sales.record") && { label: "Record sale", icon: ShoppingCart, href: `/sales?reseller=${r.id}` },
            can("stocktake.record") && { label: "Start stocktake", icon: ClipboardCheck, href: `/stocktakes/new?location=${r.locations[0]?.id ?? ""}` },
          ]} />
          {can("transfer.request") && <ButtonLink href={`/transfers/new?destination=${r.locations[0]?.id ?? ""}`} variant="primary"><ArrowLeftRight aria-hidden />Request transfer</ButtonLink>}
        </> : undefined}
        actions={staff && <>
          {can("transfer.request") && <CheckStockButton />}
          {can("reseller.initial_stock") && r.joined_with_stock !== false && <Button onClick={() => setInitialOpen(true)}><PackagePlus aria-hidden />Initial stock</Button>}
          {/* A new dealer's stock comes from the warehouse: a stock request goes for approval, then the Sales Rep delivers it. */}
          {can("stock_request.create") && r.joined_with_stock === false && <ButtonLink href={`/stock-requests/new?location=${r.locations[0]?.id ?? ""}`}><PackagePlus aria-hidden />Order stock</ButtonLink>}
          {can("sales.record") && <ButtonLink href={`/sales?reseller=${r.id}`}><ShoppingCart aria-hidden />Record sale</ButtonLink>}
          {can("stocktake.record") && <ButtonLink href={`/stocktakes/new?location=${r.locations[0]?.id ?? ""}`}><ClipboardCheck aria-hidden />Start stocktake</ButtonLink>}
          {can("transfer.request") && <ButtonLink href={`/transfers/new?destination=${r.locations[0]?.id ?? ""}`} variant="primary"><ArrowLeftRight aria-hidden />Request transfer</ButtonLink>}
        </>} />
      {r.status !== "ACTIVE" && <Alert tone="warn">This account is {humanize(r.status)}: no new replenishment dispatches or transfers. Existing obligations remain visible.</Alert>}
      <Tabs active={tab} onChange={setTab} tabs={[
        { id: "overview", label: "Overview" },
        ...(staff && can("dealer_history.read") ? [{ id: "dealer-history", label: "Dealer history" }] : []),
        { id: "stock", label: "Consignment stock" }, { id: "replenishment", label: "Replenishment" },
        { id: "sales", label: "Sales & invoices" }, { id: "transfers", label: "Transfers" },
        { id: "stocktakes", label: "Stocktakes" }, { id: "history", label: "Activity" },
        { id: "profile", label: "Profile" },
      ]} />
      {tab === "overview" && <OverviewTab reseller={r} onTab={setTab} />}
      {tab === "dealer-history" && <DealerHistoryTab resellerId={rid} canCorrect={can("initial_stock.correct")} />}
      {tab === "stock" && <StockTab reseller={r} />}
      {tab === "replenishment" && <ReplenishmentTab rid={rid} />}
      {tab === "sales" && <SalesTab rid={rid} />}
      {tab === "transfers" && <TransfersTab rid={rid} />}
      {tab === "stocktakes" && <StocktakesTab rid={rid} />}
      {tab === "history" && <ResellerHistory resellerId={rid} />}
      {tab === "profile" && <ProfileTab reseller={r} onChanged={reload} />}
      {initialOpen && <InitialStockModal reseller={r} onClose={() => setInitialOpen(false)} onDone={() => { setInitialOpen(false); reload(); setTab("stock"); }} />}
    </>
  );
}

function OverviewTab({ reseller, onTab }: { reseller: Reseller; onTab: (t: string) => void }) {
  const rid = reseller.id;
  const { data: pos } = useApi<AllocationPosition[]>("/allocations/positions", { reseller_id: rid });
  const { data: reqs } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { reseller_id: rid, open_only: true });
  const { data: sales } = useApi<Sale[]>("/sales", { reseller_id: rid });
  const { data: stocktakes } = useApi<Stocktake[]>("/stocktakes", { reseller_id: rid });
  const { data: deliveries } = useApi<Delivery[]>("/replenishment/deliveries", { reseller_id: rid, open_only: true });
  const t = useMemo(() => (pos ?? []).reduce((a, p) => ({ target: a.target + p.target_qty, on_hand: a.on_hand + p.on_hand, available: a.available + p.available,
    inbound: a.inbound + p.replenishment_in_transit + p.transfers_inbound }), { target: 0, on_hand: 0, available: 0, inbound: 0 }), [pos]);
  const outstanding = (reqs ?? []).reduce((a, r) => a + r.qty_outstanding, 0);
  const awaiting = (reqs ?? []).reduce((a, r) => a + r.qty_awaiting_supply, 0);
  const uninvoiced = (sales ?? []).flatMap((s) => s.lines).filter((l) => l.invoice_status === "UNINVOICED");
  const lastCount = (stocktakes ?? []).reduce<Stocktake | null>((a, s) => (!a || s.count_date > a.count_date ? s : a), null);
  const nextDelivery = (deliveries ?? []).filter((d) => d.status === "IN_TRANSIT").sort((a, b) => a.dispatched_at.localeCompare(b.dispatched_at))[0];

  return (
    <>
      <MetricStrip items={[
        { label: "Consignment stock", value: t.on_hand, tone: "accent", hint: `${t.available} available · target ${t.target}` },
        { label: "Outstanding replenishment", value: outstanding, hint: `${(reqs ?? []).length} open request(s)` },
        { label: "Pending backorders", value: awaiting, tone: awaiting ? "warn" : "default", hint: "Units awaiting supply" },
        { label: "Inbound", value: t.inbound, tone: "info", hint: "Deliveries and transfers on the way" },
        { label: "Sold, not invoiced", value: uninvoiced.reduce((a, l) => a + l.chargeable_qty, 0), hint: "Invoiced through Xero" },
      ]} />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <Card title="Recent sales" className="lg:col-span-2" padded={false} actions={<Button size="sm" variant="ghost" onClick={() => onTab("sales")}>View all</Button>}>
          <DataTable mobile="cards" label="Recent sales" search={false} rows={sales?.slice(0, 6)} rowKey={(s) => s.id} empty="No sales recorded yet"
            columns={[
              { key: "n", mobile: "primary" as const, header: "Sale", cell: (s) => <Link className="link" href={`/sales?sale=${s.id}`}>{s.number}</Link> },
              { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Date", cell: (s) => <span className="text-ink-secondary">{fmtDate(s.sale_date)}</span> },
              { key: "sk", mobile: "field" as const, mobileOrder: 2, header: "Tyres", className: "min-w-48 whitespace-normal", cell: (s) => <span className="text-label text-ink-secondary">{s.lines.map((l) => `${l.chargeable_qty} × ${l.product_name ?? l.sku} (${l.sku})`).join(", ")}</span> },
              { key: "inv", mobile: "status" as const, header: "Invoicing", cell: (s) => <div className="flex gap-1">{[...new Set(s.lines.map((l) => l.invoice_status))].map((st) => <Badge key={st} value={st} />)}</div> },
            ]} />
        </Card>
        <div className="space-y-4">
          <Card title="Next expected delivery" icon={Truck}>
            {nextDelivery ? (
              <div>
                <div className="flex items-center justify-between"><span className="font-medium">{nextDelivery.number}</span><Badge value={nextDelivery.status} /></div>
                <p className="mt-1 text-label text-ink-secondary">{nextDelivery.lines.reduce((a, l) => a + l.qty_dispatched, 0)} unit(s) dispatched {fmtDate(nextDelivery.dispatched_at)} to {nextDelivery.to_location_code}</p>
              </div>
            ) : <p className="text-label text-ink-muted">Nothing in transit to this dealer.</p>}
          </Card>
          <Card title="Last stocktake" icon={ClipboardCheck}>
            {lastCount ? (
              <div>
                <div className="flex items-center justify-between"><Link className="link" href={`/stocktakes/${lastCount.id}`}>{lastCount.number}</Link><Badge value={lastCount.status} /></div>
                <p className="mt-1 text-label text-ink-secondary">Counted {fmtDate(lastCount.count_date)} at <ShopLabel inline code={lastCount.location_code} withDealer={false} /> · net variance <span className={lastCount.total_variance < 0 ? "font-medium text-danger" : ""}>{lastCount.total_variance}</span></p>
              </div>
            ) : <p className="text-label text-ink-muted">No stocktake recorded yet.</p>}
          </Card>
          <Card title="Open replenishment" icon={RefreshCw} actions={<Button size="sm" variant="ghost" onClick={() => onTab("replenishment")}>View</Button>}>
            {(reqs ?? []).length ? (
              <ul className="space-y-2">
                {(reqs ?? []).slice(0, 4).map((q) => (
                  <li key={q.id} className="flex items-center justify-between gap-2 text-label">
                    <span className="min-w-0"><Link className="link" href={`/replenishment/${q.id}`}>{q.number}</Link> <span className="text-ink-muted">· {q.product_name} ({q.sku})</span></span>
                    <span className="flex shrink-0 items-center gap-2"><span className="num">{q.qty_outstanding}</span><Badge value={q.reason} /></span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-label text-ink-muted">No open replenishment.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}

function StockTab({ reseller }: { reseller: Reseller }) {
  const { can } = useAuth();
  const { data, reload } = useApi<AllocationPosition[]>("/allocations/positions", { reseller_id: reseller.id });
  const [edit, setEdit] = useState<{ location_id: number; product_id: number | ""; target: string; auto: string } | null>(null);
  const [reason, setReason] = useState("");
  const action = useAction();
  const totals = useMemo(() => (data ?? []).reduce((a, p) => ({ target: a.target + p.target_qty, on_hand: a.on_hand + p.on_hand,
    open: a.open + p.open_replenishment, unmet: a.unmet + p.remaining_unmet }), { target: 0, on_hand: 0, open: 0, unmet: 0 }), [data]);

  async function save() {
    if (!edit) return;
    const ok = await action.run(() => api.put("/allocations", { location_id: edit.location_id, product_id: edit.product_id,
      target_qty: Number(edit.target), auto_replenish: edit.auto === "true", reason }));
    if (ok) { setEdit(null); reload(); }
  }

  return (
    <Card title="Consignment stock by SKU" padded={false}
      actions={can("allocation.write") && <Button size="sm" onClick={() => { setEdit({ location_id: reseller.locations[0]?.id, product_id: "", target: "", auto: "true" }); setReason(""); }}>Add SKU target</Button>}>
      <div className="grid grid-cols-2 border-b border-line sm:grid-cols-4">
        {([["Target total", totals.target], ["On hand", totals.on_hand], ["Open replenishment", totals.open], ["Uncovered shortfall", totals.unmet]] as const).map(([k, v]) => (
          <div key={k} className="-mb-px border-r border-b border-line px-5 py-3 last:border-r-0"><div className="text-caption text-ink-muted">{k}</div><div className={cx("num text-heading font-semibold", k === "Uncovered shortfall" && v > 0 && "text-warning")}>{v}</div></div>
        ))}
      </div>
      <DataTable mobile="cards" label="Dealer stock" rows={data} rowKey={(p) => `${p.location_id}-${p.product_id}`} empty="No consignment stock or targets yet" emptyHint="Set SKU targets for this dealer, then deliver stock or post opening balances."
        columns={[
          { key: "l", mobile: "secondary" as const, header: "Shop", value: (p) => p.location_code, cell: (p) => <ShopLabel code={p.location_code} withDealer={false} /> },
          { key: "s", mobile: "primary" as const, header: "Product", value: (p) => `${p.sku} ${p.product_name}`, cell: (p) => <div className="flex items-center gap-1"><ProductCell name={p.product_name} sku={p.sku} /><StockOrigin locationId={p.location_id} productId={p.product_id} /></div> },
          { key: "t", mobile: "field" as const, mobileOrder: 2, header: "Target", align: "right", value: (p) => p.target_qty, cell: (p) => <>{p.target_qty}{!p.auto_replenish && p.allocation_id && <span title="Auto-replenish off" className="ml-1 text-caption text-ink-muted">(manual)</span>}</> },
          { key: "oh", mobile: "field" as const, mobileOrder: 1, header: "On hand", align: "right", value: (p) => p.on_hand, cell: (p) => <NumLink href={links.movements(p.product_id, p.location_id)} title="Every movement at this dealer"><Qty value={p.on_hand} zeroMuted={false} /></NumLink> },
          { key: "av", header: "Available", align: "right", value: (p) => p.available, cell: (p) => <Qty value={p.available} /> },
          { key: "rs", header: "Reserved", align: "right", cell: (p) => <NumLink href={p.reserved ? links.movements(p.product_id, p.location_id) : null} title="What it is reserved for"><Qty value={p.reserved} /></NumLink> },
          { key: "bl", header: "Blocked", align: "right", cell: (p) => <NumLink href={p.blocked ? links.movements(p.product_id, p.location_id) : null} title="When and why it was blocked"><Qty value={p.blocked} tone="danger" /></NumLink> },
          { key: "or", header: "Open replen.", align: "right", value: (p) => p.open_replenishment, cell: (p) => <NumLink href={p.open_replenishment ? links.demand(p.product_id, reseller.id) : null} title="Open requests for this tyre"><Qty value={p.open_replenishment} /></NumLink> },
          { key: "in", header: "Inbound", align: "right", cell: (p) => <NumLink href={p.replenishment_in_transit + p.transfers_inbound ? links.deliveries() : null} title="Deliveries on the way"><Qty value={p.replenishment_in_transit + p.transfers_inbound} /></NumLink> },
          { key: "un", mobile: "field" as const, mobileOrder: 3, header: "Unmet", align: "right", value: (p) => p.remaining_unmet, cell: (p) => <NumLink href={p.remaining_unmet ? links.demand(p.product_id, reseller.id) : null} title="Still waiting for supply"><Qty value={p.remaining_unmet} tone="warn" /></NumLink> },
          ...(can("allocation.write") ? [{ key: "e", mobile: "action" as const, header: "", cell: (p: AllocationPosition) => <Button size="sm" variant="ghost"
            onClick={() => { setEdit({ location_id: p.location_id, product_id: p.product_id, target: String(p.target_qty), auto: String(p.auto_replenish || !p.allocation_id) }); setReason(""); }}>Target</Button> }] : []),
        ]} />
      <Modal open={!!edit} title="Set consignment target" onClose={() => setEdit(null)}
        footer={<><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" disabled={action.busy || !edit?.product_id || edit?.target === "" || reason.trim().length < 3} onClick={save}>Save target</Button></>}>
        <Alert>{action.error}</Alert>
        {edit && <div className="space-y-3">
          <Field label="Location">{(id) => <Select id={id} value={edit.location_id} onChange={(e) => setEdit({ ...edit, location_id: Number(e.target.value) })}
            options={reseller.locations.map((l) => ({ value: l.id, label: `${shopText(l, false)} · ${l.code}` }))} />}</Field>
          <Field label="Product" required>{(id) => <ProductSelect id={id} value={edit.product_id} onChange={(v) => setEdit({ ...edit, product_id: v })} />}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Target quantity" required>{(id) => <Input id={id} type="number" min={0} value={edit.target} onChange={(e) => setEdit({ ...edit, target: e.target.value })} />}</Field>
            <Field label="Replenish automatically on sale">{(id) => <Select id={id} value={edit.auto} onChange={(e) => setEdit({ ...edit, auto: e.target.value })} options={[{ value: "true", label: "Yes" }, { value: "false", label: "No — manual" }]} />}</Field>
          </div>
          <Field label="Reason for change" required hint="Target changes are kept in an audit trail.">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        </div>}
      </Modal>
    </Card>
  );
}

function ReplenishmentTab({ rid }: { rid: number }) {
  const [openOnly, setOpenOnly] = useState("true");
  const { data } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { reseller_id: rid, open_only: openOnly === "true" });
  const byReason = (data ?? []).filter((r) => r.qty_outstanding > 0).reduce<Record<string, number>>((a, r) => ({ ...a, [r.reason]: (a[r.reason] ?? 0) + r.qty_outstanding }), {});
  return (
    <Card title="Replenishment obligations" padded={false}
      actions={<div className="flex items-center gap-3 text-caption">{Object.entries(byReason).map(([k, v]) => <span key={k}><Badge value={k} /> {v}</span>)}
        <Select aria-label="Filter" value={openOnly} onChange={(e) => setOpenOnly(e.target.value)} options={[{ value: "true", label: "Open only" }, { value: "false", label: "All" }]} /></div>}>
      <RequestsTable rows={data} />
    </Card>
  );
}

function SalesTab({ rid }: { rid: number }) {
  const { data: sales } = useApi<Sale[]>("/sales", { reseller_id: rid });
  const { data: invoices } = useApi<Invoice[]>("/invoices", { reseller_id: rid });
  return (
    <div className="space-y-4">
      <Card title="Sales" padded={false}>
        <DataTable mobile="cards" label="Sales" rows={sales?.flatMap((s) => s.lines.map((l) => ({ s, l })))} rowKey={(x) => x.l.id} empty="No sales recorded yet"
          columns={[
            { key: "n", mobile: "primary" as const, header: "Sale", value: (x) => x.s.number, cell: (x) => <Link className="link" href={`/sales?sale=${x.s.id}`}>{x.s.number}</Link> },
            { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Date", value: (x) => x.s.sale_date, cell: (x) => fmtDate(x.s.sale_date) },
            { key: "src", header: "Source", value: (x) => x.s.source, cell: (x) => saleSourceLabel(x.s.source) },
            { key: "sku", mobile: "secondary" as const, header: "SKU", value: (x) => x.l.sku, cell: (x) => <span className="sku text-label">{x.l.sku}</span> },
            { key: "q", mobile: "field" as const, mobileOrder: 2, header: "Qty", align: "right", cell: (x) => x.l.chargeable_qty },
            { key: "inv", mobile: "status" as const, header: "Invoice", value: (x) => x.l.invoice_status, cell: (x) => x.l.invoice_number ? <span className="text-caption">{x.l.invoice_number}</span> : <Badge value={x.l.invoice_status} /> },
          ]} />
      </Card>
      <Card title="Invoices" padded={false}>
        <DataTable mobile="cards" label="Invoices" search={false} rows={invoices} rowKey={(i) => i.id} empty="No invoices have been created"
          columns={[
            { key: "n", mobile: "primary" as const, header: "Invoice", cell: (i) => <Link className="link" href={`/invoices/${i.id}`}>{i.number}</Link> },
            { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Date", cell: (i) => fmtDate(i.invoice_date) },
            { key: "due", mobile: "field" as const, mobileOrder: 2, header: "Due", cell: (i) => fmtDate(i.due_date) },
            { key: "t", mobile: "field" as const, mobileOrder: 3, header: "Tyres", align: "right", cell: (i) => i.lines.reduce((a, l) => a + l.quantity, 0) },
            { key: "s", mobile: "status" as const, header: "Status", cell: (i) => <Badge value={i.status} /> },
          ]} />
      </Card>
    </div>
  );
}

function TransfersTab({ rid }: { rid: number }) {
  const { data } = useApi<Transfer[]>("/transfers", { reseller_id: rid });
  return <Card title="Incoming and outgoing transfers" padded={false}><TransfersTable rows={data} perspective={rid} /></Card>;
}

function StocktakesTab({ rid }: { rid: number }) {
  const { data } = useApi<Stocktake[]>("/stocktakes", { reseller_id: rid });
  const { can, user } = useAuth();
  return (
    <div className="space-y-4">
    {!user?.reseller_id && <StockCheckSchedule title="Next stock check" resellerId={rid} all canRecord={can("stocktake.record")} />}
    <Card title="Stocktakes" padded={false}>
      <DataTable mobile="cards" label="Stock checks" search={false} rows={data} rowKey={(s) => s.id} empty="No stocktakes yet"
        columns={[
          { key: "n", mobile: "primary" as const, header: "Stocktake", cell: (s) => <Link className="link" href={`/stocktakes/${s.id}`}>{s.number}</Link> },
          { key: "l", mobile: "secondary" as const, header: "Shop", cell: (s) => <ShopLabel code={s.location_code} withDealer={false} /> },
          { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Count date", cell: (s) => fmtDate(s.count_date) },
          { key: "by", header: "Counted by", cell: (s) => s.counted_by },
          { key: "v", mobile: "field" as const, mobileOrder: 2, header: "Net variance", align: "right", cell: (s) => <Qty value={s.total_variance} tone={s.total_variance < 0 ? "danger" : undefined} /> },
          { key: "st", mobile: "status" as const, header: "Status", cell: (s) => <Badge value={s.status} /> },
        ]} />
    </Card>
    </div>
  );
}

function ProfileTab({ reseller: r, onChanged }: { reseller: Reseller; onChanged: () => void }) {
  const { can } = useAuth();
  const [statusOpen, setStatusOpen] = useState(false);
  const [newStatus, setNewStatus] = useState(r.status === "ACTIVE" ? "ON_HOLD" : "ACTIVE");
  const [locOpen, setLocOpen] = useState(false);
  const [loc, setLoc] = useState({ name: "", address_line1: "", address_line2: "", city: "", postcode: "", contact_phone: "" });
  const action = useAction();
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card title="Profile" actions={can("reseller.write") && <Button size="sm" onClick={() => setStatusOpen(true)}>Change status</Button>}>
        <DefinitionList columns={1} items={[
          ["Account reference", r.account_ref], ["Business name", r.business_name], ["Trading name", r.trading_name],
          ["Contact", r.contact_name],
          ["Email", r.email ? <a key="e" className="link break-all whitespace-normal!" href={`mailto:${r.email}`}>{r.email}</a> : null],
          ["Phone", r.phone], ["Billing address", <span key="b" className="whitespace-pre-line">{r.billing_address ?? "—"}</span>],
          ["Tax number", r.tax_number], ["Payment terms", r.payment_terms_days !== null ? `${r.payment_terms_days} days` : "Default"],
          ["Sales representative", r.sales_rep_name], ["Status", <Badge key="s" value={r.status} />],
        ]} />
      </Card>
      <Card title="Consignment agreement">
        {r.agreement ? <DefinitionList columns={1} items={[
          ["Reference", r.agreement.reference], ["Start", fmtDate(r.agreement.start_date)], ["End", fmtDate(r.agreement.end_date)],
          ["Transfers out", humanize(r.agreement.transfer_consent)], ["Auto-replenish default", r.agreement.auto_replenish_default ? "Yes" : "No"],
          ["Notes", r.agreement.notes],
        ]} /> : <p className="text-body text-ink-muted">No agreement recorded (transfers need per-transfer consent).</p>}
      </Card>
      <div className="lg:col-span-2"><AgreementFilesCard resellerId={r.id} canEdit={can("reseller.write")} /></div>
      <Card title="Shops (delivery locations)" className="lg:col-span-2" padded={false} actions={can("reseller.write") && <Button size="sm" onClick={() => setLocOpen(true)}>Add shop</Button>}>
        <DataTable mobile="cards" label="Shops" search={false} rows={r.locations} rowKey={(l) => l.id}
          columns={[
            { key: "c", mobile: "primary" as const, header: "Code", cell: (l) => <span className="sku text-label">{l.code}</span> },
            { key: "n", mobile: "secondary" as const, mobileOrder: 1, header: "Name", cell: (l) => l.name },
            { key: "a", mobile: "secondary" as const, mobileOrder: 2, header: "Address", cell: (l) => [l.address_line1, l.city, l.region, l.postcode].filter(Boolean).join(", ") || "—" },
            { key: "s", mobile: "status" as const, header: "Status", cell: (l) => <Badge value={l.is_active ? "ACTIVE" : "CLOSED"} label={l.is_active ? "Active" : "Inactive"} /> },
          ]} />
      </Card>
      <ConfirmDialog open={statusOpen} title="Change account status" requireReason busy={action.busy} error={action.error}
        onClose={() => setStatusOpen(false)}
        onConfirm={async (reason) => { if (await action.run(() => api.post(`/resellers/${r.id}/status`, { status: newStatus, reason }))) { setStatusOpen(false); onChanged(); } }}>
        <Field label="New status">{(id) => <Select id={id} value={newStatus} onChange={(e) => setNewStatus(e.target.value)} options={["ACTIVE", "ON_HOLD", "CLOSED"].map((s) => ({ value: s, label: humanize(s) }))} />}</Field>
      </ConfirmDialog>
      <Modal open={locOpen} title="Add a shop" description={`Its code is created automatically (${r.account_ref}-NN).`} onClose={() => setLocOpen(false)}
        footer={<><Button onClick={() => setLocOpen(false)}>Cancel</Button><Button variant="primary" disabled={action.busy || !loc.name.trim() || !loc.address_line1.trim() || !loc.city.trim()}
          onClick={async () => {
            const body = { name: loc.name, address_line1: loc.address_line1, city: loc.city, address_line2: loc.address_line2 || null,
              postcode: loc.postcode || null, contact_phone: loc.contact_phone || null };
            if (await action.run(() => api.post(`/resellers/${r.id}/locations`, body))) { setLocOpen(false); invalidateReference(); onChanged(); }
          }}>Add shop</Button></>}>
        <Alert>{action.error}</Alert>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Shop name" required>{(id) => <Input id={id} value={loc.name} onChange={(e) => setLoc({ ...loc, name: e.target.value })} />}</Field>
          <Field label="Contact phone">{(id) => <Input id={id} value={loc.contact_phone} onChange={(e) => setLoc({ ...loc, contact_phone: e.target.value })} />}</Field>
          <Field label="Delivery address" required>{(id) => <Input id={id} value={loc.address_line1} onChange={(e) => setLoc({ ...loc, address_line1: e.target.value })} placeholder="Address line 1" />}</Field>
          <Field label="Address line 2">{(id) => <Input id={id} value={loc.address_line2} onChange={(e) => setLoc({ ...loc, address_line2: e.target.value })} />}</Field>
          <Field label="City" required>{(id) => <Input id={id} value={loc.city} onChange={(e) => setLoc({ ...loc, city: e.target.value })} />}</Field>
          <Field label="Postcode">{(id) => <Input id={id} value={loc.postcode} onChange={(e) => setLoc({ ...loc, postcode: e.target.value })} />}</Field>
        </div>
      </Modal>
    </div>
  );
}

/** Details every dealer should have (finding 9). Dealers created before 1.11 may lack some; they are not migrated. */
function missingDetails(r: Reseller): string[] {
  const out: string[] = [];
  if (!r.contact_name?.trim()) out.push("contact name");
  if (!r.email?.trim()) out.push("email");
  if (!r.phone?.trim()) out.push("phone");
  if (!r.billing_address?.trim()) out.push("billing address");
  if (!r.sales_rep_user_id) out.push("sales representative");
  if (!r.locations.some((l) => l.address_line1?.trim() && l.city?.trim())) out.push("a shop address and city");
  return out;
}
