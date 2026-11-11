"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { ROLE_LABELS } from "@/config/roles";
import type { ReactNode } from "react";
import { fmtDate } from "@/lib/format";
import type { ReplenishmentRequest, Transfer } from "@/lib/types";
import { MiniProgress } from "./flow";
import { ShopLabel } from "./pickers";
import { StockOrigin } from "./StockOrigin";
import { Badge, cx, DataTable, ProductCell, Qty } from "./ui";

const TRANSFER_STAGES = ["REQUESTED", "APPROVED", "IN_TRANSIT", "COMPLETED"];

/** How far a transfer has got: Requested → Approved → In transit → Received. */
export function transferProgress(t: Transfer) {
  if (t.status === "RECEIVED_WITH_DISCREPANCY") return { done: 3, failed: true };
  if (t.status === "CANCELLED" || t.status === "REJECTED") return { done: t.approved_at ? 1 : 0, failed: true };
  const i = TRANSFER_STAGES.indexOf(t.status);
  return { done: t.status === "COMPLETED" ? 4 : Math.max(i, 0) + 1, failed: false };
}

export function RequestsTable({ rows, showReseller = false, filters, empty, filterCount, onClearFilters }: {
  rows: ReplenishmentRequest[] | null; showReseller?: boolean; filters?: ReactNode; empty?: ReactNode; filterCount?: number; onClearFilters?: () => void;
}) {
  return (
    <DataTable mobile="cards" label="Replenishment requests" rows={rows} rowKey={(r) => r.id} searchPlaceholder="Search request, dealer, SKU…" filters={filters}
      filterCount={filterCount} onClearFilters={onClearFilters}
      empty={empty ?? "No replenishment requests"} emptyHint="There are currently no open replenishment requests. They appear when sales, transfers or target shortfalls create demand."
      rowClassName={(r) => r.priority === "URGENT" && r.qty_outstanding > 0 && "shadow-[inset_3px_0_0_var(--color-danger)]"}
      columns={[
        { key: "n", mobile: "primary" as const, header: "Request", mobileSort: "Request number", value: (r) => r.number, cell: (r) => (
          <div><Link className="link" href={`/replenishment/${r.id}`}>{r.number}</Link><div className="text-caption whitespace-nowrap text-ink-muted">{fmtDate(r.created_at)}</div></div>
        ) },
        ...(showReseller ? [{ key: "res", mobile: "secondary" as const, mobileOrder: 1, header: "Dealer", value: (r: ReplenishmentRequest) => r.reseller_name,
          cell: (r: ReplenishmentRequest) => <div className="min-w-0"><div className="truncate text-ink">{r.reseller_name}</div><div className="text-caption text-ink-muted">{r.location_code}</div></div> }]
          : [{ key: "l", header: "Shop", value: (r: ReplenishmentRequest) => r.location_code, cell: (r: ReplenishmentRequest) => <ShopLabel code={r.location_code} withDealer={false} /> }]),
        { key: "s", mobile: "secondary" as const, mobileOrder: 2, header: "Product", value: (r) => `${r.sku} ${r.product_name}`, cell: (r) => <div className="flex items-center gap-1"><ProductCell name={r.product_name} sku={r.sku} /><StockOrigin locationId={r.location_id} productId={r.product_id} /></div> },
        { key: "req", mobile: "field" as const, mobileOrder: 3, header: "Required", align: "right", value: (r) => r.qty_required, cell: (r) => r.qty_required },
        { key: "al", header: "Allocated", align: "right", cell: (r) => <Qty value={r.qty_allocated + r.qty_transfer_covered} /> },
        { key: "tr", header: "In transit", align: "right", cell: (r) => <Qty value={r.qty_in_transit} /> },
        { key: "aw", mobile: "field" as const, mobileOrder: 4, header: "Outstanding", align: "right", mobileSort: true, value: (r) => r.qty_awaiting_supply, cell: (r) => <Qty value={r.qty_awaiting_supply} tone="warn" /> },
        { key: "p", mobile: "field" as const, mobileOrder: 5, header: "Priority", value: (r) => r.priority, cell: (r) => <Badge value={r.priority} /> },
        { key: "why", header: "Source", value: (r) => `${r.reason} ${r.raised_by ?? ""}`, cell: (r) => <div><Badge value={r.reason} />{r.first_supply && <> <Badge value="LATEST_STOCK" label="Latest stock" /></>}<div className="mt-0.5 text-caption whitespace-nowrap text-ink-muted">{r.origin_number ?? ""}</div>
          {r.raised_by && <div className="text-caption whitespace-nowrap text-ink-secondary">Raised by {r.raised_by}{r.raised_by_role ? ` · ${ROLE_LABELS[r.raised_by_role]}` : ""}</div>}</div> },
        { key: "e", header: "Expected", value: (r) => r.expected_date, cell: (r) => <span className="whitespace-nowrap text-ink-secondary">{fmtDate(r.expected_date)}</span> },
        { key: "age", header: "Age", align: "right", mobileSort: "Age (days)", value: (r) => r.age_days, cell: (r) => <span className={r.age_days >= 14 && r.qty_outstanding > 0 ? "font-medium text-danger" : "text-ink-secondary"}>{r.age_days}d</span> },
        { key: "st", mobile: "status" as const, header: "Status", value: (r) => r.status, cell: (r) => <Badge value={r.status} /> },
      ]} />
  );
}

export function TransfersTable({ rows, perspective, filters, filterCount, onClearFilters }: {
  rows: Transfer[] | null; perspective?: number; filters?: ReactNode; filterCount?: number; onClearFilters?: () => void;
}) {
  return (
    <DataTable mobile="cards" label="Transfers" rows={rows} rowKey={(t) => t.id} filters={filters} searchPlaceholder="Search transfer, dealer, SKU…"
      filterCount={filterCount} onClearFilters={onClearFilters}
      empty="No stock transfers" emptyHint="No stock transfers have been created for this view."
      rowClassName={(t) => t.status === "RECEIVED_WITH_DISCREPANCY" && "bg-danger-soft/40"}
      columns={[
        { key: "n", mobile: "primary" as const, header: "Transfer", mobileSort: "Transfer number", value: (t) => t.number, cell: (t) => (
          <div>
            <div className="flex items-center gap-1.5"><Link className="link" href={`/transfers/${t.id}`}>{t.number}</Link>{t.urgency !== "NORMAL" && <Badge value={t.urgency} />}</div>
            <div className="text-caption whitespace-nowrap text-ink-muted">{fmtDate(t.requested_at)}</div>
          </div>
        ) },
        ...(perspective ? [{ key: "dir", mobile: "field" as const, mobileOrder: 3, header: "Direction", cell: (t: Transfer) => (t.source_reseller_id === perspective ? <Badge value="TRANSFER" label="Outgoing" /> : <Badge value="RECEIVED" tone="info" label="Incoming" />) }] : []),
        { key: "s", mobile: "secondary" as const, header: "Tyre", value: (t) => `${t.sku} ${t.product_name}`, cell: (t) => <ProductCell name={t.product_name} sku={t.sku} /> },
        { key: "route", mobile: "field" as const, mobileLabel: "Route", mobileOrder: 1, header: "From → To", value: (t) => `${t.source_reseller_name ?? ""} ${t.destination_reseller_name ?? ""}`, cell: (t) => (
          <div className="flex items-center gap-2.5">
            <div className="min-w-0">
              <div className={cx("max-w-36 truncate whitespace-nowrap", t.source_reseller_name ? "text-ink-secondary" : "text-ink-muted italic")}>{t.source_reseller_name ?? "Source not chosen"}</div>
              {t.source_location_code && <div className="text-caption text-ink-muted">{t.source_location_code}</div>}
            </div>
            <ArrowRight className="size-4 shrink-0 text-brand-text" aria-label="to" />
            <div className="min-w-0">
              <div className="max-w-36 truncate whitespace-nowrap font-medium text-ink">{t.destination_reseller_name}</div>
              {t.destination_location_code && <div className="text-caption text-ink-muted">{t.destination_location_code}</div>}
            </div>
          </div>
        ) },
        { key: "q", mobile: "field" as const, mobileOrder: 2, header: "Qty", align: "right", mobileSort: "Quantity", value: (t) => t.quantity, cell: (t) => <span className="font-medium">{t.quantity}</span> },
        { key: "why", header: "Reason", value: (t) => t.reason, cell: (t) => <div className="max-w-52 truncate text-ink-secondary" title={t.reason}>{t.reason}</div> },
        { key: "st", mobile: "status" as const, header: "Status", value: (t) => t.status, cell: (t) => {
          const p = transferProgress(t);
          return <div className="space-y-1"><Badge value={t.status} /><div><MiniProgress total={4} done={p.done} failed={p.failed} label={`Stage ${Math.min(p.done, 4)} of 4`} /></div></div>;
        } },
        { key: "ob", header: "Replacement owed", cell: (t) => t.source_request
          ? <div><Link className="link text-label" href={`/replenishment/${t.source_request.id}`}>{t.source_request.number}</Link><div className="mt-0.5"><Badge value={t.source_request.status} /></div></div>
          : <span className="text-ink-muted">—</span> },
      ]} />
  );
}
