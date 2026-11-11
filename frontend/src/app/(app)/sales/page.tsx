"use client";

import { ClipboardCheck, Plus, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Timeline } from "@/components/flow";
import { LocationSelect, ProductSelect, ResellerSelect, ShopLabel, shopText, useLocations, TyreLabel } from "@/components/pickers";
import {
  Alert, Badge, Button, ButtonLink, Card, ConfirmDialog, DataTable, DefinitionList, Drawer, Field, FilterField, Input,
  Modal, PageHeader, Select, Tabs, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, humanize, todayIso } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BILLING_LABEL, billingState, billingTrack, NON_CONSIGNMENT_LABEL, nextStep, replacementLabel, saleSourceLabel, stockTrack } from "@/lib/saleJourney";
import type { Sale, SaleLine, Stocktake } from "@/lib/types";

export default function SalesPage() {
  const params = useSearchParams();
  const router = useRouter();
  const { can, user } = useAuth();
  const [tab, setTab] = useState("sales");
  const [reseller, setReseller] = useState<number | "">(params.get("reseller") ? Number(params.get("reseller")) : "");
  const { data, error, reload } = useApi<Sale[]>("/sales", { reseller_id: reseller });
  const { data: stocktakes } = useApi<Stocktake[]>(user?.reseller_id ? null : "/stocktakes");
  const isReseller = !!user?.reseller_id;
  const [recordOpen, setRecordOpen] = useState(params.get("new") === "1" && can("sales.record"));
  const [detail, setDetail] = useState<number | null>(params.get("sale") ? Number(params.get("sale")) : null);
  const [created, setCreated] = useState<Sale | null>(null);
  const [notInvoicedOnly, setNotInvoicedOnly] = useState(false);
  const seesXero = can("invoice.reference_read");
  const rows = useMemo(() => (data && notInvoicedOnly ? data.filter((s) => billingState(s) === "NOT_INVOICED") : data), [data, notInvoicedOnly]);

  return (
    <>
      <PageHeader title={isReseller ? "My sales" : "Sales & stocktakes"}
        subtitle={isReseller ? "Report each tyre you sell so the dealership can invoice it and send replacement stock."
          : "Confirmed consignment sales are chargeable to the dealer and trigger replenishment. Replenishment never creates an invoice."}
        actions={<>
          {can("stocktake.record") && <ButtonLink href="/stocktakes/new"><ClipboardCheck aria-hidden />New stocktake</ButtonLink>}
          {(can("sales.record") || can("sales.cash")) && <Button variant="primary" onClick={() => setRecordOpen(true)}><Plus aria-hidden />{isReseller ? "Report a sale" : "Record sale"}</Button>}
        </>} />
      {!isReseller && <Tabs active={tab} onChange={setTab} tabs={[{ id: "sales", label: "Confirmed sales", count: data?.length }, { id: "stocktakes", label: "Stocktakes", count: stocktakes?.length }]} />}
      {tab === "stocktakes" && <Alert tone="info">A stocktake compares expected and counted stock. Every shortage must be classified as sold or missing before approval — a shortage is never assumed to be a sale.</Alert>}
      <Alert>{error}</Alert>
      {created && (
        <Alert tone="success">
          Recorded {created.number}: {created.total_qty} unit(s).{" "}
          {created.source === "CASH_SALE" ? <>Non-consignment sale from the warehouse; invoice record {created.lines[0]?.invoice_number ? `${created.lines[0].invoice_number} ` : ""}created{created.customer_name ? ` for ${created.customer_name}` : ""}.{can("invoice.read") && <> <Link className="underline" href="/invoices">Open invoices</Link></>}</>
          : isReseller
            ? <>Thanks, {created.lines.flatMap((l) => l.replenishment).length
                ? <>your replacement tyres are being arranged ({created.lines.flatMap((l) => l.replenishment).map((r, i) => <span key={r.id}>{i > 0 && ", "}<Link className="underline" href={`/replenishment/${r.id}`}>{r.number}</Link></span>)}).</>
                : "your sale is recorded."} TyreGrow will invoice you through Xero.</>
          : created.lines.flatMap((l) => l.replenishment).length
            ? <>Replenishment raised: {created.lines.flatMap((l) => l.replenishment).map((r) => <Link key={r.id} className="underline" href={`/replenishment/${r.id}`}>{r.number} ({r.qty_required}, {humanize(r.status)}) </Link>)}</>
            : "No replenishment raised (auto-replenish off, or target already covered)."}
        </Alert>
      )}
      {tab === "sales" && (
        <Card padded={false}>
          <DataTable mobile="cards" label="Sales" rows={rows} rowKey={(s) => s.id} onRowClick={(s) => setDetail(s.id)}
            empty={notInvoicedOnly ? "Everything here is invoiced" : isReseller ? "No sales reported yet" : "No sales recorded yet"}
            emptyHint={isReseller ? "Use “Report a sale” whenever you sell consignment stock." : "Confirmed sales reported by dealers or found in stocktakes appear here."}
            filterCount={[reseller, notInvoicedOnly].filter(Boolean).length}
            onClearFilters={() => { setReseller(""); setNotInvoicedOnly(false); }}
            filters={<>
              {!user?.reseller_id && <FilterField label="Dealer" className="w-64"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField>}
              <label className="flex items-center gap-2 text-label text-ink-secondary">
                <input type="checkbox" className="size-4 accent-ink" checked={notInvoicedOnly} onChange={(e) => setNotInvoicedOnly(e.target.checked)} />
                Not invoiced only
              </label>
            </>}
            columns={[
              { key: "n", mobile: "primary" as const, header: "Sale", mobileSort: "Sale number", value: (s) => s.number, cell: (s) => <span className="font-medium whitespace-nowrap text-ink">{s.number}</span> },
              { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Date", mobileSort: "Sale date", value: (s) => s.sale_date, cell: (s) => fmtDate(s.sale_date) },
              { key: "r", mobile: "secondary" as const, header: "Dealer", mobileSort: true, value: (s) => `${s.reseller_name} ${s.customer_name ?? ""}`, cell: (s) => <>{s.source === "CASH_SALE" ? NON_CONSIGNMENT_LABEL : s.reseller_name}{s.customer_name && <div className="text-caption text-ink-muted">{s.customer_name}{s.customer_phone ? ` · ${s.customer_phone}` : ""}</div>}</> },
              { key: "l", header: "Shop", value: (s) => s.location_code, cell: (s) => <ShopLabel code={s.location_code} withDealer={false} /> },
              { key: "src", header: "Source", value: (s) => s.source, cell: (s) => <>{saleSourceLabel(s.source)}<div className="text-caption text-ink-muted">{s.source_reference}</div></> },
              { key: "sk", mobile: "field" as const, mobileOrder: 2, header: "Tyres", className: "min-w-56 whitespace-normal", value: (s) => s.lines.map((l) => `${l.sku} ${l.product_name}`).join(" "), cell: (s) => <span className="space-y-0.5 text-caption">{s.lines.map((l) => <span key={l.id} className="block"><TyreLabel sku={l.sku} productId={l.product_id} qty={l.chargeable_qty} /></span>)}</span> },
              { key: "q", header: "Qty", align: "right", value: (s) => s.total_qty, cell: (s) => s.total_qty },
              { key: "rp", mobile: "field" as const, mobileOrder: 3, header: "Replacement", value: (s) => replacementLabel(s), cell: (s) => <span className="whitespace-nowrap text-ink-secondary">{replacementLabel(s)}</span> },
              { key: "inv", mobile: "status" as const, header: "Invoiced?", value: (s) => billingState(s) ?? "", cell: (s) => { const b = billingState(s); return b
                ? <Badge value={b === "INVOICED" ? "INVOICED" : b === "INVOICE_DRAFTED" ? "DRAFTED" : "UNINVOICED"} label={BILLING_LABEL[b]} />
                : <span className="text-ink-muted">—</span>; } },
              ...(seesXero ? [{ key: "x", header: "Xero no.", value: (s: Sale) => s.lines.map((l) => l.xero_reference ?? "").join(" "),
                cell: (s: Sale) => <span className="sku text-label">{[...new Set(s.lines.map((l) => l.xero_reference).filter(Boolean))].join(", ") || "—"}</span> }] : []),
            ]} />
        </Card>
      )}
      {tab === "stocktakes" && (
        <Card padded={false}>
          <DataTable mobile="cards" label="Stock checks" rows={stocktakes} rowKey={(s) => s.id} onRowClick={(s) => router.push(`/stocktakes/${s.id}`)}
            empty="No stocktakes yet" emptyHint="Start a stocktake at a dealer location to compare expected and counted stock."
            columns={[
              { key: "n", mobile: "primary", header: "Stocktake", value: (s) => s.number, cell: (s) => <span className="font-medium whitespace-nowrap text-ink">{s.number}</span> },
              { key: "r", mobile: "secondary", header: "Dealer", value: (s) => s.reseller_name, cell: (s) => s.reseller_name },
              { key: "l", header: "Shop", value: (s) => `${s.location_name ?? ""} ${s.location_city ?? ""} ${s.location_code}`,
                cell: (s) => <div>{s.location_name ?? s.location_code}<div className="text-caption text-ink-muted">{[s.location_city, s.location_code].filter(Boolean).join(" · ")}</div></div> },
              { key: "d", mobile: "field", mobileOrder: 1, header: "Count date", value: (s) => s.count_date, cell: (s) => fmtDate(s.count_date) },
              { key: "by", header: "Counted by", value: (s) => s.counted_by, cell: (s) => s.counted_by },
              { key: "v", mobile: "field", mobileOrder: 2, header: "Net variance", align: "right", value: (s) => s.total_variance, cell: (s) => <span className={s.total_variance < 0 ? "font-semibold text-danger" : s.total_variance > 0 ? "text-success" : "text-ink-muted"}>{s.total_variance > 0 ? "+" : ""}{s.total_variance}</span> },
              { key: "st", mobile: "status", header: "Status", value: (s) => s.status, cell: (s) => <Badge value={s.status} /> },
            ]} />
        </Card>
      )}
      {recordOpen && <RecordSaleModal onClose={() => setRecordOpen(false)} onDone={(s) => { setRecordOpen(false); setCreated(s); reload(); }} />}
      {detail !== null && <SaleDetailModal id={detail} onClose={() => setDetail(null)} onChanged={reload} />}
    </>
  );
}

function RecordSaleModal({ onClose, onDone }: { onClose: () => void; onDone: (s: Sale) => void }) {
  const params = useSearchParams();
  const { user, can } = useAuth();
  const isReseller = !!user?.reseller_id;
  const canCash = !isReseller && can("sales.cash");
  const canConsign = can("sales.record");
  const ownLocations = useLocations(["CONSIGNMENT"]);
  const [location, setLocation] = useState<number | "" | "cash">(canConsign ? "" : "cash");
  const [customer, setCustomer] = useState("");
  const [phone, setPhone] = useState("");
  const [date, setDate] = useState(todayIso());
  const [source, setSource] = useState("RESELLER_REPORT");
  const [ref, setRef] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<{ product: number | ""; qty: string }[]>([{ product: "", qty: "1" }]);
  const action = useAction();
  const preselectReseller = params.get("reseller");
  const { data: resellerLocs } = useApi<{ locations: { id: number }[] }>(preselectReseller ? `/resellers/${preselectReseller}` : null);
  const effectiveLocation = location || resellerLocs?.locations[0]?.id || (isReseller && ownLocations?.length === 1 ? ownLocations[0].id : "") || "";
  const cash = effectiveLocation === "cash";

  async function submit() {
    const saleLines = lines.filter((l) => l.product && Number(l.qty) > 0).map((l) => ({ product_id: l.product, quantity: Number(l.qty) }));
    const sale = await action.run(() => cash
      ? api.post<Sale>("/sales/cash", { sale_date: date, customer_name: customer.trim() || null, customer_phone: phone.trim() || null, notes: notes || null, lines: saleLines })
      : api.post<Sale>("/sales", { location_id: effectiveLocation, sale_date: date, source, source_reference: ref || null, notes: notes || null, lines: saleLines }));
    if (sale) onDone(sale);
  }
  return (
    <Modal open wide title={isReseller ? "Report a sale" : "Record confirmed sale"} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={action.busy || !effectiveLocation || !lines.some((l) => l.product)} onClick={submit}>{action.busy ? "Recording…" : isReseller ? "Report sale" : "Record sale"}</Button></>}>
      <Alert>{action.error}</Alert>
      <Alert tone="info">{isReseller
        ? "Report tyres you have sold to your customers. Replacement stock is arranged automatically, and TyreGrow invoices you through Xero."
        : cash ? "Non-consignment sale: a customer (a nearby shop or any dealer) buys and pays at the warehouse. Stock leaves the warehouse now, nothing is replaced, and an invoice record is created to complete in Xero."
        : "Only confirmed sales belong here. Missing stock found during a count should go through a stocktake — it is never assumed sold."}</Alert>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={isReseller ? "Location" : "Dealer location"} required>{(id) => canCash
          ? <Select id={id} value={effectiveLocation} onChange={(e) => setLocation(e.target.value === "cash" ? "cash" : e.target.value ? Number(e.target.value) : "")}
              placeholder={canConsign ? "Select location…" : undefined}
              options={[{ value: "cash", label: `${NON_CONSIGNMENT_LABEL}` },
                ...(canConsign ? (ownLocations ?? []).map((l) => ({ value: l.id, label: `${shopText(l, false)} · ${l.code}` })) : [])]} />
          : <LocationSelect id={id} types={["CONSIGNMENT"]} value={effectiveLocation === "cash" ? "" : effectiveLocation} onChange={setLocation} />}</Field>
        <Field label="Sale date" required>{(id) => <Input id={id} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
        {cash && <>
          <Field label="Customer name">{(id) => <Input id={id} value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="e.g. Corner Garage" />}</Field>
          <Field label="Customer phone">{(id) => <Input id={id} value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
        </>}
        {!isReseller && !cash && <Field label="Source">{(id) => <Select id={id} value={source} onChange={(e) => setSource(e.target.value)}
          options={[{ value: "RESELLER_REPORT", label: "Reported by dealer" }, { value: "REP_VISIT", label: "Sales rep visit" }, { value: "OTHER", label: "Other" }]} />}</Field>}
        {!cash && <Field label="Source reference">{(id) => <Input id={id} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="e.g. email 12 Oct, docket #" />}</Field>}
      </div>
      <div className="space-y-2">
        <div className="text-caption font-medium text-ink-secondary">{cash ? "Tyres sold from the warehouse" : "Tyres sold"}</div>
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_90px_auto] gap-2">
            <ProductSelect value={l.product} onChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, product: v } : x)))} />
            <Input type="number" min={1} aria-label="Quantity" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} />
            <Button size="sm" variant="ghost" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} disabled={lines.length === 1}><X aria-hidden /></Button>
          </div>
        ))}
        <Button size="sm" onClick={() => setLines((ls) => [...ls, { product: "", qty: "1" }])}>Add line</Button>
      </div>
      <Field label="Notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
    </Modal>
  );
}

function SaleDetailModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { can, user } = useAuth();
  const isDealer = !!user?.reseller_id;
  // D12: the full billing track for the invoicing roles and the dealer; everyone else sees invoiced yes / not yet.
  const fullBilling = isDealer || can("invoice.reference_read");
  const { data: s, error, reload } = useApi<Sale>(`/sales/${id}`);
  const [reverse, setReverse] = useState<SaleLine | null>(null);
  const [qty, setQty] = useState("1");
  const action = useAction();
  return (
    <Drawer open title={s ? `Sale ${s.number}` : "Sale"} description={s ? `${s.reseller_name} · ${s.location_code}` : undefined} onClose={onClose}>
      <Alert>{error}</Alert>
      {s && <>
        <DefinitionList columns={1} items={[["Sale date", fmtDate(s.sale_date)], ["Source", <>{saleSourceLabel(s.source)}{s.source_reference && ` (${s.source_reference})`}</>],
          ["Recorded by", s.recorded_by], ["Quantity", s.total_qty]]} />
        {(() => { const next = nextStep(s, can, isDealer); return next && <Alert tone="info"><b className="font-semibold">Next step:</b> {next}</Alert>; })()}
        <div className="grid grid-cols-1 gap-4 rounded-control border border-line p-4 sm:grid-cols-2">
          <div><div className="mb-2 text-caption font-medium tracking-wide text-ink-muted uppercase">Stock</div><Timeline steps={stockTrack(s)} /></div>
          <div><div className="mb-2 text-caption font-medium tracking-wide text-ink-muted uppercase">Billing</div>
            {fullBilling ? <Timeline steps={billingTrack(s)} />
              : <p className="text-body">{billingState(s) === "INVOICED" ? <b className="font-semibold text-success">Invoiced ✓</b> : <span className="text-ink-secondary">Not yet invoiced</span>}</p>}
          </div>
        </div>
        <DataTable mobile="cards" label="Tyres on this sale" search={false} rows={s.lines} rowKey={(l) => l.id}
          columns={[
            { key: "sku", mobile: "primary" as const, header: "Tyre", className: "min-w-48 whitespace-normal", cell: (l) => <TyreLabel sku={l.sku} productId={l.product_id} /> },
            { key: "q", mobile: "field" as const, mobileOrder: 1, header: "Qty", align: "right", cell: (l) => <>{l.chargeable_qty}{l.reversed_qty > 0 && <span className="text-caption text-ink-muted"> ({l.reversed_qty} reversed)</span>}</> },
            { key: "inv", mobile: "status" as const, header: "Invoice", cell: (l) => fullBilling
              ? l.invoice_number ?? <Badge value={l.invoice_status} />
              : l.invoiced ? <span className="text-success">Invoiced ✓</span> : <span className="text-ink-muted">Not yet</span> },
            { key: "rep", mobile: "field" as const, mobileLabel: "Replacement", mobileOrder: 2, header: "Replenishment", cell: (l) => l.replenishment.length ? l.replenishment.map((r) => <Link key={r.id} className="block text-caption link" href={`/replenishment/${r.id}`}>{r.number} · {r.qty_required} · {humanize(r.status)}</Link>) : <span className="text-caption text-ink-muted">none</span> },
            ...(can("sales.reverse") ? [{ key: "a", mobile: "action" as const, header: "", cell: (l: SaleLine) => l.invoice_status === "UNINVOICED" && l.chargeable_qty > 0 && <Button size="sm" variant="ghost" onClick={() => { setReverse(l); setQty("1"); action.setError(null); }}>Reverse</Button> }] : []),
          ]} />
      </>}
      <ConfirmDialog open={!!reverse} title="Reverse sale quantity" danger requireReason busy={action.busy} error={action.error} confirmLabel="Post reversal"
        message="Posts a compensating movement back into the dealer's stock and withdraws the matching not-yet-dispatched replenishment. Only uninvoiced lines can be reversed."
        onClose={() => setReverse(null)}
        onConfirm={async (reason) => { if (await action.run(() => api.post(`/sales/lines/${reverse!.id}/reverse`, { quantity: Number(qty), reason }))) { setReverse(null); reload(); onChanged(); } }}>
        <Field label={`Quantity (max ${reverse?.chargeable_qty})`}>{(fid) => <Input id={fid} type="number" min={1} max={reverse?.chargeable_qty} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
      </ConfirmDialog>
    </Drawer>
  );
}
