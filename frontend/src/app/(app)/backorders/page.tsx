"use client";

import Link from "next/link";
import { ArrowLeftRight, Plus, ShoppingCart } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { CheckStockButton } from "@/components/CheckStock";
import { StockAvailability } from "@/components/StockAvailability";
import { FilteredTo } from "@/components/NumLink";
import { useMemo, useState } from "react";
import { LocationSelect, ProductSelect, ResellerSelect, useLocations, TyreLabel, useTyreName } from "@/components/pickers";
import {
  Alert, Badge, Button, ButtonLink, Card, cx, DataTable, Field, FilterField, Input, MetricStrip, MobileActionBar, Modal,
  PageHeader, Qty, QuickFilters, Select, Tabs, Textarea,
} from "@/components/ui";
import { uiConfig } from "@/config/branding";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, humanize, todayIso } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Proposal } from "@/lib/types";
import { vocab } from "@/lib/terms";
import { branding } from "@/config/branding";

interface BackorderRow {
  request_id: number; number: string; reseller_id: number; reseller_name: string; location_id: number; location_code: string; product_id: number; sku: string;
  reason: string; origin_number: string | null; qty_required: number; qty_outstanding: number; qty_allocated: number; qty_in_transit: number;
  qty_transfer_covered: number; qty_awaiting_supply: number; priority: string; expected_date: string | null; status: string; age_days: number;
}
interface Report {
  rows: BackorderRow[];
  totals: { requests: number; qty_outstanding: number; qty_allocated: number; qty_in_transit: number; qty_transfer_covered: number; qty_awaiting_supply: number };
  by_reason: Record<string, number>;
}

/** Mandatory report 11.2 plus allocation of newly received stock to open backorders. */
export default function BackordersPage() {
  const { can, user } = useAuth();
  const [tab, setTab] = useState("report");
  return (
    <>
      <PageHeader title="Backorders" subtitle="Outstanding replenishment demand. A backorder is demand, not stock; it closes only when delivered or cancelled with authority."
        actions={can("transfer.request") && !user?.reseller_id && <CheckStockButton />} />
      <Tabs active={tab} onChange={setTab} tabs={[{ id: "report", label: "Outstanding" },
        ...(can("replenishment.manage") && !user?.reseller_id ? [{ id: "allocate", label: "Allocate received stock" }] : [])]} />
      {tab === "report" ? <Outstanding /> : <AllocationProposal />}
    </>
  );
}

type QF = "all" | "urgent" | "overdue" | "sale" | "transfer";

function isOverdue(r: BackorderRow, today: string) {
  return (!!r.expected_date && r.expected_date < today) || (!r.expected_date && r.age_days >= uiConfig.backorderOverdueDays);
}

function Outstanding() {
  const { can, user } = useAuth();
  const params = useSearchParams();
  const product = params.get("product_id") ? Number(params.get("product_id")) : undefined;
  const tyreName = useTyreName();
  const [reseller, setReseller] = useState<number | "">(params.get("reseller") ? Number(params.get("reseller")) : "");
  const [reason, setReason] = useState("");
  const [awaiting, setAwaiting] = useState("true");
  const [qf, setQf] = useState<QF>("all");
  const { data, error, reload } = useApi<Report>("/reports/backorders", { reseller_id: reseller, reason, awaiting_supply_only: awaiting === "true", product_id: product });
  const [manual, setManual] = useState(params.get("request") === "1" && can("replenishment.request"));
  const today = todayIso();
  const weekAhead = new Date(new Date(`${today}T00:00:00Z`).getTime() + 7 * 864e5).toISOString().slice(0, 10);
  const tests: Record<QF, (r: BackorderRow) => boolean> = {
    all: () => true, urgent: (r) => r.priority === "URGENT" || r.priority === "HIGH", overdue: (r) => isOverdue(r, today),
    sale: (r) => r.reason === "SALE", transfer: (r) => r.reason === "TRANSFER",
  };
  const all = data?.rows ?? [];
  const count = (k: QF) => all.filter(tests[k]).length;
  const rows = useMemo(() => data?.rows.filter(tests[qf]) ?? null, [data, qf]); // eslint-disable-line react-hooks/exhaustive-deps
  const expectedThisWeek = all.filter((r) => r.expected_date && r.expected_date >= today && r.expected_date <= weekAhead);

  return (
    <>
      <Alert>{error}</Alert>
      {product && <FilteredTo label={`Demand for ${tyreName({ productId: product }) ?? `this ${vocab.item}`}`} clearHref="/backorders" />}
      {data && (
        <MetricStrip items={[
          { label: "Total backorders", value: data.totals.requests, hint: Object.entries(data.by_reason).map(([k, v]) => `${humanize(k)} ${v}`).join(" · ") || "No open demand" },
          { label: "Units outstanding", value: data.totals.qty_awaiting_supply, tone: data.totals.qty_awaiting_supply ? "warn" : "ok",
            hint: `${data.totals.qty_allocated + data.totals.qty_transfer_covered} allocated · ${data.totals.qty_in_transit} in transit` },
          { label: "Urgent", value: count("urgent"), tone: count("urgent") ? "danger" : "default", hint: "Urgent or high priority" },
          { label: "Overdue", value: count("overdue"), tone: count("overdue") ? "danger" : "default", hint: `Past expected date or ${uiConfig.backorderOverdueDays}+ days old` },
          { label: "Expected this week", value: expectedThisWeek.reduce((a, r) => a + r.qty_awaiting_supply, 0), hint: `${expectedThisWeek.length} request(s) with supply due` },
        ]} />
      )}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <QuickFilters value={qf} onChange={setQf} options={[
          { id: "all", label: "All", count: all.length }, { id: "urgent", label: "Urgent", count: count("urgent") },
          { id: "overdue", label: "Overdue", count: count("overdue") }, { id: "sale", label: "From sales", count: count("sale") },
          { id: "transfer", label: "From transfers", count: count("transfer") },
        ]} />
        {can("replenishment.request") && <Button size="sm" variant={user?.reseller_id ? "primary" : "secondary"} onClick={() => setManual(true)}><Plus aria-hidden />{user?.reseller_id ? "Request replenishment" : "Manual request"}</Button>}
      </div>
      <Card padded={false}>
        <DataTable mobile="cards" label="Backorders" rows={rows} rowKey={(r) => r.request_id} pageSize={100}
          empty="No outstanding backorders" emptyHint="All replenishment demand is covered by stock, allocations or transfers."
          rowClassName={(r) => (r.priority === "URGENT" || isOverdue(r, today)) && "shadow-[inset_3px_0_0_var(--color-danger)]"}
          filterCount={[reseller, reason, awaiting !== "true"].filter(Boolean).length}
          onClearFilters={() => { setReseller(""); setReason(""); setAwaiting("true"); }}
          filters={<>
            {!user?.reseller_id && <FilterField label={vocab.Partner} className="w-56"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField>}
            <FilterField label="Reason" className="w-40"><Select aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="All reasons"
              options={["SALE", "TRANSFER", "TARGET_SHORTFALL", "MANUAL"].map((x) => ({ value: x, label: humanize(x) }))} /></FilterField>
            <FilterField label="Scope" className="w-52"><Select aria-label="Scope" value={awaiting} onChange={(e) => setAwaiting(e.target.value)}
              options={[{ value: "true", label: "Awaiting supply only" }, { value: "false", label: "All open (incl. allocated)" }]} /></FilterField>
          </>}
          columns={[
            { key: "n", mobile: "primary", header: "Request", mobileSort: "Request number", value: (r) => r.number, cell: (r) => <Link className="link" href={`/replenishment/${r.request_id}`}>{r.number}</Link> },
            { key: "r", mobile: "secondary", mobileOrder: 1, header: vocab.Partner, value: (r) => r.reseller_name, cell: (r) => <div className="min-w-0"><div className="truncate">{r.reseller_name}</div><div className="text-caption text-ink-muted">{r.location_code}</div></div> },
            { key: "s", mobile: "secondary", mobileOrder: 2, header: "SKU", value: (r) => r.sku, cell: (r) => <span className="sku text-label whitespace-nowrap text-ink-secondary">{r.sku}</span> },
            { key: "why", header: "Source", value: (r) => r.reason, cell: (r) => (
              <div className="flex items-center gap-2">
                {r.reason === "TRANSFER" ? <ArrowLeftRight className="size-3.5 text-info" aria-hidden /> : r.reason === "SALE" ? <ShoppingCart className="size-3.5 text-info" aria-hidden /> : null}
                <div><Badge value={r.reason} /><div className="mt-0.5 text-caption whitespace-nowrap text-ink-muted">{r.origin_number}</div></div>
              </div>
            ) },
            { key: "o", header: "Required", align: "right", value: (r) => r.qty_outstanding, cell: (r) => r.qty_outstanding },
            { key: "al", header: "Allocated", align: "right", cell: (r) => <Qty value={r.qty_allocated + r.qty_transfer_covered} /> },
            { key: "tr", header: "In transit", align: "right", cell: (r) => <Qty value={r.qty_in_transit} /> },
            { key: "aw", mobile: "field", mobileOrder: 3, header: "Outstanding", align: "right", mobileSort: true, value: (r) => r.qty_awaiting_supply, cell: (r) => <Qty value={r.qty_awaiting_supply} tone="warn" /> },
            { key: "p", mobile: "field", mobileOrder: 4, header: "Urgency", value: (r) => r.priority, cell: (r) => <Badge value={r.priority} /> },
            { key: "age", header: "Age", align: "right", mobileSort: "Age (days)", value: (r) => r.age_days, cell: (r) => <span className={r.age_days >= uiConfig.backorderOverdueDays ? "font-semibold text-danger" : "text-ink-secondary"}>{r.age_days}d</span> },
            { key: "e", header: "Expected", value: (r) => r.expected_date, cell: (r) => r.expected_date
              ? <span className={cx("whitespace-nowrap", r.expected_date < today ? "font-medium text-danger" : "text-ink-secondary")}>{fmtDate(r.expected_date)}</span>
              : <span className="whitespace-nowrap text-ink-muted">Not set</span> },
            { key: "st", mobile: "status", header: "Status", value: (r) => r.status, cell: (r) => <Badge value={r.status} /> },
            // Cover a backorder from another dealer's stock: the transfer form opens linked to this backorder. Not on the phone card
            // (it is full); there the request page carries the same action.
            ...(can("transfer.request") && !user?.reseller_id ? [{ key: "cover", mobile: "hidden" as const, header: <span className="sr-only">Actions</span>,
              cell: (r: BackorderRow) => r.qty_awaiting_supply > 0 && (
                <ButtonLink size="sm" variant="ghost" href={`/transfers/new?${new URLSearchParams({ destination: String(r.location_id), product: String(r.product_id),
                  qty: String(r.qty_awaiting_supply), request: String(r.request_id), reason: `Covers backorder ${r.number}` })}`}>
                  <ArrowLeftRight aria-hidden />Cover with a transfer<span className="sr-only"> for {r.number}</span></ButtonLink>
              ) }] : []),
          ]} />
      </Card>
      {manual && <ManualRequest onClose={() => setManual(false)} onDone={() => { setManual(false); reload(); }} />}
      {!user?.reseller_id && rows && rows.length > 0 && (
        <div className="mt-4"><StockAvailability title="Stock for these backorders" productIds={[...new Set(rows.map((r) => r.product_id))].slice(0, 50)}
          requested={rows.reduce<Record<number, number>>((a, r) => ({ ...a, [r.product_id]: (a[r.product_id] ?? 0) + r.qty_awaiting_supply }), {})} /></div>
      )}
    </>
  );
}

function ManualRequest({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { user } = useAuth();
  const reseller = !!user?.reseller_id;
  const locations = useLocations(["CONSIGNMENT"]);
  const [picked, setLocation] = useState<number | "">("");
  // A reseller with a single location never has to choose it.
  const location = picked || (reseller && locations?.length === 1 ? locations[0].id : "");
  const [product, setProduct] = useState<number | "">("");
  const [qty, setQty] = useState("1");
  const [priority, setPriority] = useState("NORMAL");
  const [reason, setReason] = useState("");
  const [approverNote, setApproverNote] = useState("");
  // Dealer and Sales Rep requests wait for approval (finding 22).
  const needsApproval = reseller || user?.role === "SALES_REP";
  const action = useAction();
  return (
    <Modal open title={reseller ? "Request replenishment" : "Manual replenishment request"} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={action.busy || !location || !product || reason.trim().length < 3}
        onClick={async () => { if (await action.run(() => api.post("/replenishment/requests", { location_id: location, product_id: product, quantity: Number(qty), priority, reason,
          ...(needsApproval ? { approver_note: approverNote.trim() || null } : {}) }))) onDone(); }}>Create request</Button></>}>
      <Alert>{action.error}</Alert>
      <Alert tone="info">{reseller
        ? `Request stock you need beyond what is already on its way. Requests are limited to your agreed stock levels; ${branding.companyName} confirms and dispatches.`
        : "Requests above the uncovered target shortfall need override permission, so demand is not duplicated."}</Alert>
      <Field label={reseller ? "Location" : `${vocab.Partner} location`} required>{(id) => <LocationSelect id={id} types={["CONSIGNMENT"]} value={location} onChange={setLocation} />}</Field>
      <Field label="Product" required>{(id) => <ProductSelect id={id} value={product} onChange={setProduct} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Quantity">{(id) => <Input id={id} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        <Field label="Priority">{(id) => <Select id={id} value={priority} onChange={(e) => setPriority(e.target.value)} options={(reseller ? ["HIGH", "NORMAL", "LOW"] : ["URGENT", "HIGH", "NORMAL", "LOW"]).map((p) => ({ value: p, label: humanize(p) }))} />}</Field>
      </div>
      <Field label={reseller ? "Why do you need it?" : "Reason"} required>{(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
      {needsApproval && (
        <Field label="Note for the approver" hint="Optional. Anything the warehouse should know before approving, e.g. a customer is waiting.">
          {(id) => <Textarea id={id} rows={2} value={approverNote} onChange={(e) => setApproverNote(e.target.value)} />}
        </Field>
      )}
    </Modal>
  );
}

function AllocationProposal() {
  const { data, error, reload } = useApi<Proposal[]>("/replenishment/allocation-proposal");
  const [qty, setQty] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const action = useAction();
  async function confirm() {
    const lines = (data ?? []).map((p) => ({ request_id: p.request_id, quantity: Number(qty[p.request_id] ?? p.proposed_qty) })).filter((l) => l.quantity > 0);
    const r = await action.run(() => api.post<unknown[]>("/replenishment/allocation-proposal/confirm", { lines }));
    if (r) { setMsg(`Reserved stock for ${lines.length} request(s). Dispatch them from Replenishment → Pick & dispatch.`); setQty({}); reload(); }
  }
  return (
    <>
    <Card padded={false} title="Proposed allocation of available warehouse stock" subtitle="Highest priority first, then oldest"
      actions={<Button size="sm" variant="primary" className={cx(!!data?.length && "max-lg:hidden")} disabled={action.busy || !data?.length} onClick={confirm}>Confirm allocations</Button>}>
      <div className="p-3 pb-0">
        <Alert>{error ?? action.error}</Alert><Alert tone="success">{msg}</Alert>
        <p className="mb-2 text-body text-ink-secondary">Nothing is reserved until you confirm; adjust quantities to honour urgent or contractual commitments.</p>
      </div>
      <DataTable mobile="cards" label="Proposed allocations" search={false} rows={data} rowKey={(p) => p.request_id} empty="No available warehouse stock matches open backorders."
        columns={[
          { key: "n", mobile: "primary", header: "Request", cell: (p) => <Link className="link" href={`/replenishment/${p.request_id}`}>{p.request_number}</Link> },
          { key: "r", mobile: "secondary", mobileOrder: 1, header: vocab.Partner, cell: (p) => <>{p.reseller_name}<div className="text-caption text-ink-muted">{p.location_code}</div></> },
          { key: "s", mobile: "secondary", mobileOrder: 2, header: vocab.Item, className: "min-w-48 whitespace-normal", cell: (p) => <TyreLabel sku={p.sku} productId={p.product_id} /> },
          { key: "p", mobile: "status", header: "Priority", cell: (p) => <Badge value={p.priority} /> },
          { key: "c", header: "Raised", cell: (p) => fmtDate(p.created_at) },
          { key: "a", mobile: "field", mobileOrder: 3, header: "Awaiting", align: "right", cell: (p) => p.awaiting_supply },
          { key: "q", mobile: "field", mobileOrder: 4, header: "Allocate", cell: (p) => <Input className="w-20" type="number" min={0} max={p.awaiting_supply} aria-label={`Allocate ${p.request_number}`}
            value={qty[p.request_id] ?? String(p.proposed_qty)} onChange={(e) => setQty((x) => ({ ...x, [p.request_id]: e.target.value }))} /> },
        ]} />
    </Card>
    {/* Phones and tablets in portrait: Confirm docks at the bottom while there are proposals to confirm. */}
    {!!data?.length && <MobileActionBar desktop="hidden">
      <Button variant="primary" disabled={action.busy} onClick={confirm}>Confirm allocations</Button>
    </MobileActionBar>}
    {!!data?.length && <div className="mt-4"><StockAvailability title="Stock for the proposed allocations" productIds={[...new Set(data.map((p) => p.product_id))].slice(0, 50)}
      requested={data.reduce<Record<number, number>>((a, p) => ({ ...a, [p.product_id]: (a[p.product_id] ?? 0) + p.awaiting_supply }), {})} /></div>}
    </>
  );
}
