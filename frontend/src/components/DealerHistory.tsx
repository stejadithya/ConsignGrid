"use client";

import Link from "next/link";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { DealerHistory } from "@/lib/types";
import { InitialStockCorrections } from "./InitialStockCorrection";
import { Alert, Badge, Card, DataTable, DefinitionList, Loading, MetricStrip } from "./ui";
import { branding } from "@/config/branding";

/** How stock first reached the dealer, in plain words. */
const ARRIVAL: Record<string, string> = {
  OPENING_BALANCE: "Initial stock loaded",
  REPLENISHMENT_RECEIPT: "Delivery from the warehouse",
  TRANSFER_RECEIPT: "Transfer from another dealer",
};
const arrival = (txnType: string) => ARRIVAL[txnType] ?? humanize(txnType);

/** Dealer history at a glance (Warehouse and Relationship Managers): when the dealer joined and with what stock,
 *  new or existing, the first consignment, and sales so far. canCorrect (Relationship Manager, Administrator) adds the
 *  initial stock entries with their corrections and the Correct button. */
export function DealerHistoryTab({ resellerId, canCorrect = false }: { resellerId: number; canCorrect?: boolean }) {
  const { data: h, error, reload } = useApi<DealerHistory>(`/resellers/${resellerId}/history-summary`);
  if (error) return <Alert>{error}</Alert>;
  if (!h) return <Loading />;
  const existing = h.dealer_type === "EXISTING";
  const total = h.onboarding_stock.reduce((a, l) => a + l.quantity, 0);
  const corrected = h.onboarding_stock.some((l) => l.recorded != null);
  return (
    <div className="space-y-4">
      <MetricStrip items={[
        { label: "Onboarded", value: fmtDate(h.onboarded_at), hint: h.onboarded_by ? `Added by ${h.onboarded_by}` : undefined },
        { label: "Dealer type", value: existing ? "Existing" : "New", hint: existing ? `Joined holding ${branding.companyName} stock` : "Started with no stock" },
        { label: "Tyres sold to date", value: h.units_sold, hint: `${h.sales_count} sale${h.sales_count === 1 ? "" : "s"} (after reversals)` },
        { label: "Last sale", value: h.last_sale ? fmtDate(h.last_sale.sale_date) : "None yet",
          hint: h.last_sale ? `${h.last_sale.number} · ${h.last_sale.units} tyre${h.last_sale.units === 1 ? "" : "s"}` : undefined },
      ]} />
      <Card title="Details">
        <DefinitionList items={[
          ["Onboarded", <>{fmtDateTime(h.onboarded_at)}{h.onboarded_by && <span className="text-ink-secondary"> · {h.onboarded_by}</span>}</>],
          ["New or existing", <Badge key="t" value={existing ? "ACTIVE" : "OPEN"} label={existing ? "Existing dealer (joined with stock)" : "New dealer"} />],
          ["First consignment", h.first_stock
            ? <>{fmtDate(h.first_stock.occurred_at)} · {arrival(h.first_stock.txn_type)}{h.first_stock.reference_number && <span className="text-ink-secondary"> ({h.first_stock.reference_number})</span>}</>
            : "No stock has reached this dealer yet"],
          ["Tyres sold to date", `${h.units_sold} in ${h.sales_count} sale${h.sales_count === 1 ? "" : "s"}`],
          ["Last sale", h.last_sale
            ? <><Link className="link" href={`/sales?sale=${h.last_sale.id}`}>{h.last_sale.number}</Link> · {fmtDate(h.last_sale.sale_date)} · {h.last_sale.units} tyre{h.last_sale.units === 1 ? "" : "s"}</>
            : "No sales yet"],
        ]} />
      </Card>
      <Card padded={false} title={h.onboarding_stock_kind === "INITIAL_STOCK" ? "Onboarded with this stock" : "First delivery"}
        subtitle={h.onboarding_stock_at
          ? `${h.onboarding_stock_kind === "INITIAL_STOCK" ? "Initial stock loaded" : "Received"} ${fmtDate(h.onboarding_stock_at)} · ${total} tyre${total === 1 ? "" : "s"}`
            + (h.corrections ? ` · corrected ${h.corrections} time${h.corrections === 1 ? "" : "s"}` : "")
          : "No stock yet"}>
        <DataTable mobile="cards" label="Onboarding stock" search={false} rows={h.onboarding_stock} rowKey={(l) => l.product_id}
          empty="No stock yet" emptyHint="The first tyres this dealer receives appear here."
          columns={[
            { key: "n", mobile: "primary", header: "Tyre", cell: (l) => <div><div className="font-medium">{l.name}</div><div className="sku text-label text-ink-secondary">{l.sku}</div></div> },
            ...(corrected ? [{ key: "r", mobile: "field" as const, header: "First entered", numeric: true, cell: (l: DealerHistory["onboarding_stock"][number]) => l.recorded ?? l.quantity }] : []),
            { key: "q", mobile: "field", header: corrected ? "After corrections" : "Quantity", numeric: true, cell: (l) => l.quantity },
          ]} />
      </Card>
      {canCorrect && <InitialStockCorrections resellerId={resellerId} onCorrected={reload} />}
    </div>
  );
}
