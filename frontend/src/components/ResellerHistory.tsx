"use client";

import Link from "next/link";
import { useState } from "react";
import { fmtDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Alert, Badge, Card, DataTable, Field, Input } from "./ui";
import { ShopLabel, TyreLabel } from "./pickers";

interface HistoryRow {
  occurred_at: string;
  transaction_number: string;
  category: string;
  location_code: string;
  sku: string;
  qty_in: number;
  qty_out: number;
  running_balance: number;
  reference_type: string | null;
  reference_id: number | null;
  reference_number: string | null;
  reason: string | null;
  actor: string | null;
  invoice_numbers: string[];
  transfer: null | { id: number; number: string; status: string; source: string; destination: string; reason: string;
    approved_by: string | null; approval_notes: string | null; source_consent_reference: string | null; linked_backorder: string | null };
}

interface History {
  reseller: { id: number; name: string; account_ref: string };
  opening_balances: { location_code: string; sku: string; quantity: number }[];
  rows: HistoryRow[];
  closing_balances: { key: string; quantity: number }[];
  outstanding_obligations: { request_id: number; number: string; reason: string; origin_number: string | null;
    location_code: string; sku: string; qty_outstanding: number; qty_awaiting_supply: number; status: string }[];
  outstanding_by_reason: Record<string, number>;
  outstanding_total: number;
}

function refLink(r: HistoryRow) {
  if (!r.reference_number) return "—";
  const href = r.reference_type === "consignment_sale" ? `/sales?sale=${r.reference_id}`
    : r.reference_type === "transfer" ? `/transfers/${r.reference_id}`
    : r.reference_type === "stocktake" ? `/stocktakes/${r.reference_id}` : null;
  return href ? <Link className="link" href={href}>{r.reference_number}</Link> : r.reference_number;
}

/** Report 11.3: chronological reseller ledger with running SKU balances and outstanding obligations. */
export function ResellerHistory({ resellerId }: { resellerId: number }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const { data, error } = useApi<History>(`/reports/resellers/${resellerId}/transactions`, { date_from: from, date_to: to });
  return (
    <div className="space-y-4">
      <Alert>{error}</Alert>
      <div className="no-print flex flex-wrap gap-3">
        <div className="w-44"><Field label="From">{(id) => <Input id={id} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field></div>
        <div className="w-44"><Field label="To">{(id) => <Input id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}</Field></div>
      </div>
      {data && data.opening_balances.length > 0 && (
        <Card title="Opening balances for period">
          <div className="flex flex-wrap gap-2 text-body">{data.opening_balances.map((o) => (
            <span key={`${o.location_code}-${o.sku}`} className="rounded bg-neutral-soft px-2 py-0.5"><ShopLabel inline code={o.location_code} withDealer={false} /> · <TyreLabel sku={o.sku} />: <b className="num">{o.quantity}</b></span>))}</div>
        </Card>
      )}
      <Card title="Transactions" padded={false}>
        <DataTable label="Stock history" rows={data?.rows} rowKey={(r) => `${r.transaction_number}-${r.location_code}-${r.sku}`} pageSize={100}
          empty="No stock movements in this period"
          columns={[
            { key: "d", pin: true, header: "When", value: (r) => r.occurred_at, cell: (r) => <span className="whitespace-nowrap">{fmtDateTime(r.occurred_at)}</span> },
            { key: "c", header: "Event", value: (r) => r.category, cell: (r) => r.category === "OPENING_BALANCE" ? "Initial stock (backorder)"
              : r.category === "INITIAL_STOCK_CORRECTION" ? "Initial stock corrected" : humanize(r.category) },
            { key: "l", header: "Shop", value: (r) => r.location_code, cell: (r) => <ShopLabel code={r.location_code} withDealer={false} /> },
            { key: "s", header: "Tyre", value: (r) => r.sku, className: "min-w-48 whitespace-normal", cell: (r) => <TyreLabel sku={r.sku} /> },
            { key: "in", header: "In", align: "right", cell: (r) => (r.qty_in ? <span className="text-success">+{r.qty_in}</span> : "") },
            { key: "out", header: "Out", align: "right", cell: (r) => (r.qty_out ? <span className="text-danger">−{r.qty_out}</span> : "") },
            { key: "bal", header: "Balance", align: "right", cell: (r) => <b>{r.running_balance}</b> },
            { key: "ref", header: "Reference", value: (r) => r.reference_number, cell: refLink },
            { key: "det", header: "Details", value: (r) => `${r.invoice_numbers.join(" ")} ${r.transfer?.number ?? ""} ${r.reason ?? ""}`, cell: (r) => (
              <div className="text-caption text-ink-secondary">
                {r.category === "SALE" && (r.invoice_numbers.length ? <>Invoiced: {r.invoice_numbers.join(", ")}</> : <Badge value="UNINVOICED" />)}
                {r.transfer && (
                  <div>{r.transfer.source} → {r.transfer.destination}<br />
                    Reason: {r.transfer.reason}; approved by {r.transfer.approved_by ?? "—"}
                    {r.transfer.linked_backorder && <>; source owed via {r.transfer.linked_backorder}</>}</div>
                )}
                {!r.transfer && r.category !== "SALE" && r.reason}
              </div>) },
          ]} />
      </Card>
      <Card title={`Outstanding obligations (${data?.outstanding_total ?? 0} units)`} padded={false}
        actions={data && <div className="flex gap-2 text-caption">{Object.entries(data.outstanding_by_reason).map(([k, v]) => <span key={k}><Badge value={k} /> {v}</span>)}</div>}>
        <DataTable mobile="cards" label="Replenishment for this dealer" search={false} rows={data?.outstanding_obligations} rowKey={(o) => o.request_id} empty="Nothing outstanding"
          columns={[
            { key: "n", mobile: "primary", header: "Request", cell: (o) => <Link className="link" href={`/replenishment/${o.request_id}`}>{o.number}</Link> },
            { key: "r", header: "Reason", cell: (o) => <Badge value={o.reason} /> },
            { key: "o", header: "Origin", cell: (o) => o.origin_number ?? "—" },
            { key: "l", header: "Shop", cell: (o) => <ShopLabel code={o.location_code} withDealer={false} /> },
            { key: "s", mobile: "secondary", header: "Tyre", className: "min-w-48 whitespace-normal", cell: (o) => <TyreLabel sku={o.sku} /> },
            { key: "q", mobile: "field", mobileOrder: 1, header: "Outstanding", align: "right", cell: (o) => o.qty_outstanding },
            { key: "a", mobile: "field", mobileOrder: 2, header: "Awaiting supply", align: "right", cell: (o) => o.qty_awaiting_supply },
            { key: "st", mobile: "status", header: "Status", cell: (o) => <Badge value={o.status} /> },
          ]} />
      </Card>
    </div>
  );
}
