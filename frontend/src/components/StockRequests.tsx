"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ROLE_LABELS } from "@/config/roles";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { RoleCode, StockRequest, StockRequestStatus } from "@/lib/types";
import { ResellerSelect } from "./pickers";
import { Alert, Badge, ButtonLink, Card, DataTable, FilterField, PageHeader, QuickFilters } from "./ui";
import { vocab } from "@/lib/terms";

export const STATUS_LABEL: Record<StockRequestStatus, string> = {
  DRAFT: "Draft", SUBMITTED: "Submitted", UNDER_REVIEW: "Under review", APPROVED: "Approved",
  PARTIALLY_APPROVED: "Partially approved", REJECTED: "Rejected", READY_FOR_SHIPMENT: "Ready for shipment",
  SHIPPED: "Shipped", DELIVERED: "Delivered", CANCELLED: "Cancelled",
};

/** What a dealer sees instead of "Rejected" (D5). */
export const NOT_AVAILABLE = "Not available right now";

/** Status label; dealers see "Not available right now" rather than "Rejected". */
export function statusLabel(status: StockRequestStatus, dealer: boolean) {
  return dealer && status === "REJECTED" ? NOT_AVAILABLE : STATUS_LABEL[status];
}

export function StockRequestBadge({ status }: { status: StockRequestStatus }) {
  const { user } = useAuth();
  return <Badge value={status} label={statusLabel(status, !!user?.reseller_id)} />;
}

export function roleLabel(role: string | null | undefined) {
  return role ? ROLE_LABELS[role as RoleCode] ?? role : "";
}

export type StockRequestView = "mine" | "pending" | "approved" | "shipments" | "all";

const VIEWS: Record<StockRequestView, { title: string; subtitle: string; empty: string; hint: string }> = {
  mine: {
    title: "My stock requests", get subtitle() { return `Requests you raised (${vocab.partners} see every request for their account), from draft to delivery.`; },
    empty: "No stock requests yet", hint: "Create a request with one or more SKUs; the Central Team reviews it before stock is reserved.",
  },
  pending: {
    title: "Pending approval", subtitle: "Submitted requests waiting for the Central Team to review, approve, partially approve or reject.",
    empty: "Nothing waiting for approval", hint: "Submitted requests appear here.",
  },
  approved: {
    title: "Approved requests", subtitle: "Approved stock is reserved in the warehouse and waiting to be picked, packed and shipped.",
    empty: "No approved requests to ship", hint: "Requests appear here once the Central Team approves them.",
  },
  shipments: {
    title: "Shipments", subtitle: "Requests ready for shipment, on the way, or delivered.",
    empty: "No shipments yet", hint: "Shipped requests appear here with carrier and tracking details.",
  },
  all: {
    title: "All stock requests", subtitle: "Every consignment stock request you can see.",
    empty: "No stock requests", hint: "Requests appear here once created.",
  },
};

const STATUS_FILTERS: Record<StockRequestView, { id: string; label: string; statuses: StockRequestStatus[] }[]> = {
  mine: [
    { id: "open", label: "Open", statuses: ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PARTIALLY_APPROVED", "READY_FOR_SHIPMENT", "SHIPPED"] },
    { id: "done", label: "Closed", statuses: ["DELIVERED", "REJECTED", "CANCELLED"] },
  ],
  pending: [],
  approved: [],
  shipments: [
    { id: "ready", label: "Ready to ship", statuses: ["READY_FOR_SHIPMENT"] },
    { id: "transit", label: "In transit", statuses: ["SHIPPED"] },
    { id: "delivered", label: "Delivered", statuses: ["DELIVERED"] },
  ],
  all: [],
};

/** Requests table shared by My Requests / Pending Approval / Approved / Shipments. */
export function StockRequestList({ view }: { view: StockRequestView }) {
  const { user, can } = useAuth();
  const router = useRouter();
  const [reseller, setReseller] = useState<number | "">("");
  const [qf, setQf] = useState("all");
  const { data, error } = useApi<StockRequest[]>("/stock-requests", { view, reseller_id: reseller || undefined });
  const cfg = VIEWS[view];
  const filters = STATUS_FILTERS[view];
  const active = filters.find((f) => f.id === qf);
  const rows = data ? data.filter((r) => !active || active.statuses.includes(r.status)) : null;
  const staff = !user?.reseller_id;

  return (
    <>
      <PageHeader eyebrow="Consignment" title={cfg.title} subtitle={cfg.subtitle}
        actions={can("stock_request.create") && <ButtonLink href="/stock-requests/new" variant="primary"><Plus aria-hidden />Create request</ButtonLink>} />
      <Alert>{error}</Alert>
      <Card padded={false}>
        <DataTable mobile="cards" label="Stock requests" rows={rows} rowKey={(r) => r.id} searchPlaceholder={`Search request, ${vocab.partner}, requester…`}
          onRowClick={(r) => router.push(`/stock-requests/${r.id}`)}
          empty={cfg.empty} emptyHint={cfg.hint}
          quickFilters={filters.length > 0 && <QuickFilters value={qf} onChange={setQf} options={[
            { id: "all", label: "All", count: data?.length },
            ...filters.map((f) => ({ id: f.id, label: f.label, count: data?.filter((r) => f.statuses.includes(r.status)).length })),
          ]} />}
          filterCount={reseller ? 1 : 0} onClearFilters={() => setReseller("")}
          filters={staff ? <FilterField label={vocab.Partner} className="w-56"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField> : undefined}
          columns={[
            { key: "n", mobile: "primary" as const, header: "Request", mobileSort: "Request number", value: (r) => r.number, cell: (r) => (
              <div>
                <Link href={`/stock-requests/${r.id}`} className="font-medium text-ink hover:underline hover:decoration-brand hover:decoration-2 hover:underline-offset-4" onClick={(e) => e.stopPropagation()}>{r.number}</Link>
                <div className="text-caption text-ink-muted">{fmtDateTime(r.created_at)}</div>
              </div>
            ) },
            ...(staff ? [{ key: "r", mobile: "secondary" as const, header: vocab.Partner, value: (r: StockRequest) => r.reseller_name, cell: (r: StockRequest) => (
              <div><div>{r.reseller_name}</div><div className="text-caption text-ink-muted">{r.location_code}</div></div>
            ) }] : []),
            { key: "by", header: "Requested by", value: (r) => r.created_by, cell: (r) => (
              <div><div>{r.created_by}</div><div className="text-caption text-ink-muted">{roleLabel(r.created_by_role)}</div></div>
            ) },
            { key: "need", mobile: "field" as const, mobileOrder: 2, header: "Required", value: (r) => r.required_date ?? "", cell: (r) => <span className="text-ink-secondary">{fmtDate(r.required_date)}</span> },
            { key: "sku", header: "SKUs", align: "right", value: (r) => r.line_count, cell: (r) => r.line_count },
            { key: "q", mobile: "field" as const, mobileOrder: 1, header: "Requested", align: "right", value: (r) => r.qty_requested, cell: (r) => <span className="num font-medium">{r.qty_requested}</span> },
            { key: "a", header: "Approved", align: "right", value: (r) => r.qty_approved, cell: (r) => r.decision ? <span className="num">{r.qty_approved}</span> : <span className="text-ink-muted">—</span> },
            { key: "s", header: "Shipped", align: "right", value: (r) => r.qty_shipped, cell: (r) => r.qty_shipped ? <span className="num">{r.qty_shipped}</span> : <span className="text-ink-muted">—</span> },
            { key: "p", mobile: "field" as const, mobileOrder: 3, header: "Priority", value: (r) => r.priority, cell: (r) => <Badge value={r.priority} /> },
            { key: "st", mobile: "status" as const, header: "Status", value: (r) => STATUS_LABEL[r.status], cell: (r) => <StockRequestBadge status={r.status} /> },
          ]} />
      </Card>
    </>
  );
}
