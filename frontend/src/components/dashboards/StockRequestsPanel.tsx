"use client";

import { CheckCheck, ClipboardCheck, ClipboardList, FilePlus2, PackageCheck, Truck } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { StockRequest, StockRequestSummary } from "@/lib/types";
import { StockRequestBadge } from "../StockRequests";
import { ButtonLink, Card, DataTable } from "../ui";
import { Section, WorkQueue, type QueueItem } from "./shared";
import { vocab } from "@/lib/terms";

type Focus = "approve" | "ship" | "request";

/** Consignment stock request queue for a role dashboard: what needs approving, shipping, or is on its way. */
export function StockRequestsPanel({ focus }: { focus: Focus }) {
  const { can, user } = useAuth();
  const { data: s } = useApi<StockRequestSummary>("/stock-requests/summary");
  const view = focus === "approve" ? "pending" : focus === "ship" ? "approved" : "mine";
  const { data: rows } = useApi<StockRequest[]>("/stock-requests", { view, limit: 6 });
  const c = s?.by_status;
  const items: QueueItem[] = [
    ...(focus !== "request" ? [{ label: "Pending approval", value: s?.pending_approval ?? "—", href: "/stock-requests/pending", icon: ClipboardCheck, tone: "warn" as const, hint: "Submitted, not decided" }] : []),
    { label: "Approved, to ship", value: s?.to_ship ?? "—", href: "/stock-requests/approved", icon: CheckCheck, tone: "info", hint: `${c?.READY_FOR_SHIPMENT ?? 0} packed and ready` },
    { label: "In transit", value: s?.in_transit ?? "—", href: "/stock-requests/shipments", icon: Truck, tone: "info", hint: "Shipped, awaiting delivery" },
    ...(focus === "request" ? [
      { label: "My open requests", value: s?.my_open ?? "—", href: "/stock-requests", icon: ClipboardList, hint: "Draft to shipped" },
      { label: "Delivered", value: c?.DELIVERED ?? "—", href: "/stock-requests/shipments", icon: PackageCheck, tone: "ok" as const },
    ] : [{ label: "Delivered", value: c?.DELIVERED ?? "—", href: "/stock-requests/shipments", icon: PackageCheck, tone: "ok" as const }]),
  ];
  const title = focus === "approve" ? "Waiting for your approval" : focus === "ship" ? "Approved — reserve, pick and ship" : user?.reseller_id ? "My stock requests" : "Requests I raised";
  return (
    <Section title="Consignment stock requests" description="Multi-SKU requests reviewed by the Central Team before stock is reserved"
      actions={can("stock_request.create") && <ButtonLink size="sm" href="/stock-requests/new"><FilePlus2 aria-hidden />Create request</ButtonLink>}>
      <WorkQueue items={items} />
      <Card title={title} padded={false} className="mt-4"
        actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href={view === "mine" ? "/stock-requests" : `/stock-requests/${view}`}>View all</Link>}>
        <DataTable mobile="cards" label="Stock requests" search={false} rows={rows} rowKey={(r) => r.id} pageSize={6}
          empty={focus === "approve" ? "Nothing waiting for approval" : focus === "ship" ? "Nothing approved to ship" : "No stock requests yet"}
          emptyHint={focus === "request" ? "Create a request for one or more SKUs; you are notified as it moves along." : undefined}
          columns={[
            { key: "n", mobile: "primary" as const, header: "Request", cell: (r) => <Link className="link font-medium" href={`/stock-requests/${r.id}`}>{r.number}</Link> },
            ...(user?.reseller_id ? [] : [{ key: "r", mobile: "secondary" as const, header: vocab.Partner, cell: (r: StockRequest) => r.reseller_name }]),
            { key: "by", header: "Requested by", cell: (r) => <span className="text-ink-secondary">{r.created_by}</span> },
            { key: "d", mobile: "field" as const, mobileOrder: 2, header: "Required", cell: (r) => <span className="text-ink-secondary">{fmtDate(r.required_date)}</span> },
            { key: "q", mobile: "field" as const, mobileOrder: 1, header: "Units", align: "right", cell: (r) => <Link className="link num" href={`/stock-requests/${r.id}`}>{r.qty_requested}</Link> },
            { key: "s", mobile: "status" as const, header: "Status", cell: (r) => <StockRequestBadge status={r.status} /> },
          ]} />
      </Card>
    </Section>
  );
}
