"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ResellerSelect, ShopLabel, TyreLabel } from "@/components/pickers";
import {
  Alert, Badge, Button, Card, cx, DataTable, FilterField, MetricStrip, MobileActionBar, PageHeader, Select,
  TableCheckbox, Tabs,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Invoice, UninvoicedLine } from "@/lib/types";
import { vocab } from "@/lib/terms";

/** Invoice records are completed in Xero (finding 24): an issued record is "Invoiced in Xero". */
const RECORD_STATUS: Record<string, string> = { DRAFT: "Draft", ISSUED: "Invoiced in Xero", VOID: "Void" };

export default function InvoicesPage() {
  const { can, user } = useAuth();
  const router = useRouter();
  const seesXero = can("invoice.reference_read");
  const [tab, setTab] = useState(can("invoice.create") ? "uninvoiced" : "invoices");
  const [status, setStatus] = useState("");
  const [reseller, setReseller] = useState<number | "">("");
  const { data: invoices, error } = useApi<Invoice[]>("/invoices", { status, reseller_id: reseller });
  const { data: uninvoiced, reload } = useApi<UninvoicedLine[]>("/invoices/uninvoiced", { reseller_id: reseller });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const action = useAction();
  const selectedRows = useMemo(() => (uninvoiced ?? []).filter((l) => selected.has(l.sale_line_id)), [uninvoiced, selected]);
  const selectedResellers = new Set(selectedRows.map((l) => l.reseller_id));

  async function create() {
    const inv = await action.run(() => api.post<Invoice>("/invoices", { reseller_id: [...selectedResellers][0], sale_line_ids: [...selected] }));
    if (inv) { setSelected(new Set()); reload(); router.push(`/invoices/${inv.id}`); }
  }
  // Who has sold what since their last invoice: one row per reseller (the dashboard "Sales awaiting invoice" drill-down).
  const byReseller = useMemo(() => {
    const m = new Map<number, { reseller_id: number; reseller_name: string | null; lines: number[]; units: number; oldest: number; skus: Map<string, number> }>();
    for (const l of uninvoiced ?? []) {
      const r = m.get(l.reseller_id) ?? { reseller_id: l.reseller_id, reseller_name: l.reseller_name, lines: [] as number[], units: 0, oldest: 0, skus: new Map<string, number>() };
      r.lines.push(l.sale_line_id);
      r.units += l.quantity;
      r.oldest = Math.max(r.oldest, l.age_days);
      const sku = l.sku ?? "—";
      r.skus.set(sku, (r.skus.get(sku) ?? 0) + l.quantity);
      m.set(l.reseller_id, r);
    }
    return [...m.values()].sort((a, b) => b.oldest - a.oldest);
  }, [uninvoiced]);
  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <>
      <PageHeader title="Invoices" subtitle={`An invoice record lists the sold ${vocab.items} to bill in Xero. Create the invoice in Xero, then mark the record as invoiced with its Xero number. Replenishment deliveries and transfers never create invoice lines.`} />
      <Tabs active={tab} onChange={setTab} tabs={[
        ...(can("invoice.create") ? [{ id: "uninvoiced", label: "Sold, not invoiced", count: uninvoiced?.length }] : []),
        { id: "invoices", label: "Invoice records" }]} />
      <Alert>{error ?? action.error}</Alert>
      {tab === "uninvoiced" && (
        <Card padded={false} className="mb-4" title="Who to invoice" subtitle={`${vocab.Items} sold by each ${vocab.partner} and not yet invoiced. Select ${vocab.aPartner} to pick all their lines for one invoice.`}>
          <DataTable mobile="cards" label={`${vocab.Partners} to invoice`} search={false} rows={uninvoiced ? byReseller : null} rowKey={(r) => r.reseller_id} pageSize={50}
            empty="Nothing to invoice" emptyHint={`When ${vocab.partners} sell ${vocab.items}, they appear here until invoiced.`}
            rowClassName={(r) => r.lines.length > 0 && r.lines.every((id) => selected.has(id)) && "bg-brand-soft"}
            columns={[
              { key: "r", mobile: "primary" as const, header: vocab.Partner, cell: (r) => <Link className="link font-medium" href={`/resellers/${r.reseller_id}`}>{r.reseller_name}</Link> },
              { key: "u", mobile: "field" as const, mobileLabel: `${vocab.Items} sold`, mobileOrder: 1, header: `${vocab.Items} sold (units)`, align: "right", cell: (r) => <span className="num text-body-lg font-semibold">{r.units}</span> },
              { key: "k", header: `By ${vocab.item}`, className: "min-w-56 whitespace-normal", cell: (r) => (
                <span className="space-y-0.5 text-caption text-ink-secondary">{[...r.skus].map(([sku, q]) => <span key={sku} className="block"><TyreLabel sku={sku} qty={q} /></span>)}</span>
              ) },
              { key: "o", mobile: "field" as const, mobileOrder: 2, header: "Oldest sale", align: "right", cell: (r) => <span className={r.oldest >= 30 ? "font-medium text-danger" : "text-ink-secondary"}>{r.oldest}d</span> },
              ...(can("invoice.create") ? [{ key: "x", mobile: "action" as const, header: <span className="sr-only">Select</span>, cell: (r: (typeof byReseller)[number]) => (
                <Button size="sm" onClick={() => setSelected(new Set(r.lines))}>Select {r.lines.length} line{r.lines.length === 1 ? "" : "s"}</Button>
              ) }] : []),
            ]} />
        </Card>
      )}
      {tab === "uninvoiced" && (
        <Card padded={false} title="Confirmed sales awaiting invoice"
          actions={<Button variant="primary" size="sm" className={cx(selected.size > 0 && "max-lg:hidden")} disabled={action.busy || selected.size === 0 || selectedResellers.size !== 1} onClick={create}>
            {selectedResellers.size > 1 ? `Select one ${vocab.partner}` : `Create invoice record (${selected.size} line${selected.size === 1 ? "" : "s"})`}</Button>}>
          <DataTable mobile="cards" label="Sold, not invoiced" rows={uninvoiced} rowKey={(l) => l.sale_line_id} pageSize={100}
            empty="Nothing to invoice" emptyHint="Confirmed sales that have not been invoiced appear here."
            filterCount={reseller ? 1 : 0} onClearFilters={() => { setReseller(""); setSelected(new Set()); }}
            filters={<FilterField label={vocab.Partner} className="w-64"><ResellerSelect value={reseller} onChange={(v) => { setReseller(v); setSelected(new Set()); }} /></FilterField>}
            columns={[
              { key: "x", mobile: "status" as const, header: <TableCheckbox label="Select all" checked={!!uninvoiced?.length && selected.size === uninvoiced.length}
                onChange={(e) => setSelected(e.target.checked ? new Set((uninvoiced ?? []).map((l) => l.sale_line_id)) : new Set())} />,
                cell: (l) => <TableCheckbox label={`Select ${l.sale_number} ${l.sku}`} checked={selected.has(l.sale_line_id)} onChange={() => toggle(l.sale_line_id)} /> },
              { key: "r", mobile: "secondary" as const, header: vocab.Partner, value: (l) => l.reseller_name, cell: (l) => l.reseller_name },
              { key: "s", mobile: "primary" as const, header: "Sale", value: (l) => l.sale_number, cell: (l) => <Link className="link" href={`/sales?sale=${l.sale_id}`}>{l.sale_number}</Link> },
              { key: "d", mobile: "field" as const, mobileOrder: 3, header: "Sale date", mobileSort: true, value: (l) => l.sale_date, cell: (l) => fmtDate(l.sale_date) },
              { key: "loc", header: vocab.Site, value: (l) => l.location_code, cell: (l) => <ShopLabel code={l.location_code} withDealer={false} /> },
              { key: "sku", mobile: "field" as const, mobileOrder: 1, header: vocab.Item, value: (l) => l.sku, className: "min-w-48 whitespace-normal", cell: (l) => <TyreLabel sku={l.sku} /> },
              { key: "q", mobile: "field" as const, mobileOrder: 2, header: "Qty", align: "right", cell: (l) => l.quantity },
              { key: "a", header: "Age", align: "right", value: (l) => l.age_days, cell: (l) => `${l.age_days}d` },
            ]} />
        </Card>
      )}
      {/* Phones and tablets in portrait: while lines are selected, Create docks at the bottom. */}
      {tab === "uninvoiced" && selected.size > 0 && (
        <MobileActionBar desktop="hidden">
          <Button variant="primary" disabled={action.busy || selectedResellers.size !== 1} onClick={create}>
            {selectedResellers.size > 1 ? `Select one ${vocab.partner}` : `Create invoice record (${selected.size} line${selected.size === 1 ? "" : "s"})`}</Button>
        </MobileActionBar>
      )}
      {tab === "invoices" && invoices && (
        <MetricStrip items={[
          { label: "Draft", value: invoices.filter((i) => i.status === "DRAFT").length, hint: "Waiting to be invoiced in Xero" },
          { label: "Invoiced in Xero", value: invoices.filter((i) => i.status === "ISSUED").length },
          { label: `${vocab.Items} invoiced`, value: invoices.filter((i) => i.status === "ISSUED").reduce((a, i) => a + i.lines.reduce((b, l) => b + (l.is_active ? l.quantity : 0), 0), 0) },
          { label: "Void", value: invoices.filter((i) => i.status === "VOID").length },
        ]} />
      )}
      {tab === "uninvoiced" && uninvoiced && (
        <MetricStrip items={[
          { label: "Lines awaiting invoice", value: uninvoiced.length },
          { label: "Units", value: uninvoiced.reduce((a, l) => a + l.quantity, 0) },
          { label: vocab.Partners, value: byReseller.length, tone: "accent" },
          { label: "Oldest", value: uninvoiced.length ? `${Math.max(...uninvoiced.map((l) => l.age_days))}d` : "—", hint: "Days since sale" },
        ]} />
      )}
      {tab === "invoices" && (
        <Card padded={false}>
          <DataTable mobile="cards" label="Invoice records" rows={invoices} rowKey={(i) => i.id} onRowClick={(i) => router.push(`/invoices/${i.id}`)}
            empty="No invoice records yet" emptyHint="Invoice records are created from confirmed sales under “Sold, not invoiced”."
            filterCount={[reseller, status].filter(Boolean).length}
            onClearFilters={() => { setReseller(""); setStatus(""); }}
            filters={<>
              {!user?.reseller_id && <FilterField label={vocab.Partner} className="w-64"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField>}
              <FilterField label="Status" className="w-44"><Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses" options={["DRAFT", "ISSUED", "VOID"].map((s) => ({ value: s, label: RECORD_STATUS[s] }))} /></FilterField>
            </>}
            columns={[
              { key: "n", mobile: "primary" as const, header: "Record", mobileSort: "Record number", value: (i) => i.number, cell: (i) => <span className="font-medium whitespace-nowrap text-ink">{i.number}</span> },
              { key: "r", mobile: "secondary" as const, header: vocab.Partner, value: (i) => i.bill_to_name, cell: (i) => <>{i.bill_to_name}<div className="sku text-label text-ink-secondary">{i.bill_to_account_ref}</div></> },
              { key: "d", mobile: "field" as const, mobileOrder: 1, header: "Created", value: (i) => i.invoice_date, cell: (i) => fmtDate(i.invoice_date) },
              { key: "t", mobile: "field" as const, mobileOrder: 2, header: vocab.Items, align: "right", value: (i) => i.lines.reduce((a, l) => a + l.quantity, 0), cell: (i) => <span className="font-semibold">{i.lines.reduce((a, l) => a + l.quantity, 0)}</span> },
              { key: "s", mobile: "status" as const, header: "Status", value: (i) => i.status, cell: (i) => <Badge value={i.status} label={RECORD_STATUS[i.status]} /> },
              ...(seesXero ? [{ key: "x", header: "Xero no.", value: (i: Invoice) => i.xero_reference ?? i.external_reference ?? "",
                cell: (i: Invoice) => <span className="sku text-label">{i.xero_reference ?? i.external_reference ?? "—"}</span> }] : []),
            ]} />
        </Card>
      )}
    </>
  );
}
