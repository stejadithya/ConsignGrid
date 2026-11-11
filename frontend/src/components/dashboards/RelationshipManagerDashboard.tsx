"use client";

import {
  ArrowLeftRight, FileSpreadsheet, Building2, CircleAlert, ClipboardCheck, Clock, Plus, ReceiptText, RefreshCw, ShoppingCart, Store,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { branding, uiConfig } from "@/config/branding";
import { useAuth } from "@/lib/auth";
import { fmtDate, todayIso } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  AllocationPosition, Dashboard, ReplenishmentRequest, ResellerSummary, Sale, Stocktake, StockRequest, StockRequestSummary, Transfer,
} from "@/lib/types";
import { CheckStockButton } from "../CheckStock";
import { EXPORT_URL } from "../ProductImport";
import { FlowInline } from "../flow";
import { Alert, Badge, buttonClass, ButtonLink, Card, DataTable, Loading } from "../ui";
import {
  ActivityList, AttentionList, DashboardHeader, JobList, plural, RoleBanner, Section, thisMonth, type ActivityItem,
  type AttentionItem,
} from "./shared";
import { StockCheckAlerts } from "./StockCheckAlerts";
import { StockCheckSchedule } from "../StockCheckSchedule";
import { vocab } from "@/lib/terms";

/** The owner's view of the business: money, decisions waiting, how each dealer is doing, and what needs attention. */
export function RelationshipManagerDashboard() {
  const { user, can } = useAuth();
  const { data: d, error } = useApi<Dashboard>("/reports/dashboard");
  const { data: resellers } = useApi<ResellerSummary[]>("/resellers");
  const { data: requests } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { open_only: true });
  const { data: transfers } = useApi<Transfer[]>("/transfers", { open_only: true });
  const { data: positions } = useApi<AllocationPosition[]>("/allocations/positions");
  const { data: sales } = useApi<Sale[]>("/sales");
  const { data: srs } = useApi<StockRequestSummary>("/stock-requests/summary");
  const { data: stocktakes } = useApi<Stocktake[]>("/stocktakes");
  const { data: pendingRequests } = useApi<StockRequest[]>("/stock-requests", { view: "pending" });

  const attention = useMemo(() => buildAttention(d, positions), [d, positions]);
  const month = useMemo(() => thisMonth(sales), [sales]);
  const monthUnits = month.reduce((a, s) => a + s.total_qty, 0);

  // Each dealer this month: sales, stock held, what they are waiting for.
  const dealers = useMemo(() => {
    const by = new Map<number, { id: number; name: string; units: number; stock: number; waiting: number }>();
    for (const r of resellers ?? []) if (r.status !== "CLOSED") by.set(r.id, { id: r.id, name: r.business_name, units: 0, stock: 0, waiting: 0 });
    for (const s of month) { const x = by.get(s.reseller_id); if (x) x.units += s.total_qty; }
    for (const p of positions ?? []) { const x = by.get(p.reseller_id); if (x) x.stock += p.on_hand; }
    for (const r of requests ?? []) { const x = by.get(r.reseller_id); if (x) x.waiting += r.qty_awaiting_supply; }
    return [...by.values()].sort((a, b) => b.units - a.units || b.stock - a.stock);
  }, [resellers, month, positions, requests]);

  const activity = useMemo<ActivityItem[] | null>(() => {
    if (!sales || !requests) return null;
    return [
      ...sales.map((s) => ({ key: `s${s.id}`, icon: ShoppingCart, at: s.recorded_at, href: `/sales?sale=${s.id}`,
        title: <>Sale <b className="font-medium">{s.number}</b> · {s.reseller_name}</>, detail: `${s.total_qty} unit(s)` })),
      ...requests.map((r) => ({ key: `r${r.id}`, icon: RefreshCw, at: r.created_at, href: `/replenishment/${r.id}`,
        title: <>Replenishment <b className="font-medium">{r.number}</b> · {r.reseller_name}</>, detail: `${r.qty_required} × ${r.product_name} (${r.sku})` })),
    ].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 8);
  }, [sales, requests]);

  if (!user) return null;
  const onHold = (resellers ?? []).filter((r) => r.status === "ON_HOLD").length;
  const shortLocations = new Set((positions ?? []).filter((p) => p.remaining_unmet > 0).map((p) => p.location_id)).size;
  const checksWaiting = (stocktakes ?? []).filter((s) => s.status === "AWAITING_RESELLER").length;
  const sentToMe = (pendingRequests ?? []).filter((x) => x.escalated_to_user_id === user.id);

  return (
    <>
      <DashboardHeader name={user.full_name} subtitle={`How ${branding.companyName} is doing today: money, decisions waiting for you and your ${vocab.partners}.`}
        actions={<>
          {can("transfer.request") && <CheckStockButton />}
          {can("catalogue.import") && <a href={EXPORT_URL} download title="Edit or add rows, then use Import from Excel."
            className={buttonClass()}>
            <FileSpreadsheet className="size-4" aria-hidden />Export SKUs</a>}
          {can("reseller.write") && <ButtonLink href="/resellers?new=1"><Plus aria-hidden />New {vocab.partner}</ButtonLink>}
          {can("transfer.request") && <ButtonLink href="/transfers/new" variant="primary"><ArrowLeftRight aria-hidden />New transfer</ButtonLink>}
        </>} />
      <Alert>{error}</Alert>
      {!d && !error && <Loading label="Loading dashboard…" />}
      {d && (
        <>
          <RoleBanner theme="owner" figures={[
            { label: "Sold, not invoiced", value: d.sales_awaiting_invoicing.qty.toLocaleString(), href: "/invoices",
              hint: `${vocab.Items} to invoice through Xero`, tone: d.sales_awaiting_invoicing.qty ? "warn" : undefined },
            { label: `${vocab.Items} sold this month`, value: monthUnits.toLocaleString(), href: "/sales", hint: plural(month.length, "sale") },
            { label: `Stock at ${vocab.partners}`, value: d.consignment.on_hand.toLocaleString(), href: "/consignment", hint: `${d.consignment.available.toLocaleString()} available to sell` },
            { label: "Warehouse available", value: (d.warehouse?.available ?? 0).toLocaleString(), href: "/inventory", hint: `${(d.warehouse?.on_hand ?? 0).toLocaleString()} on hand` },
            { label: "Waiting for supply", value: d.backorders.qty_awaiting_supply.toLocaleString(), href: "/backorders",
              hint: plural(d.backorders.requests, "open request"), tone: d.backorders.qty_awaiting_supply ? "warn" : undefined },
          ]} />
          <StockCheckAlerts />
          <StockCheckSchedule title={`Stock checks due at ${vocab.partners}`} canRecord={can("stocktake.record")} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
            <Section title="Decisions waiting for you" className="xl:col-span-2" description="Each line opens the screen to act on it">
              <JobList jobs={[
                { label: "Approvals sent to you", value: sentToMe.length, hint: sentToMe.length ? sentToMe.map((x) => `${x.number} · ${x.reseller_name}`).slice(0, 2).join(", ") : "The warehouse sends requests that need you",
                  href: sentToMe.length === 1 ? `/stock-requests/${sentToMe[0].id}` : "/stock-requests/pending", icon: ClipboardCheck, urgent: sentToMe.length > 0 },
                { label: "Approve stock requests", value: srs?.pending_approval ?? 0, hint: `${vocab.Partners} waiting for your yes / no`, href: "/stock-requests/pending", icon: ClipboardCheck },
                { label: `Approve transfers between ${vocab.partners}`, value: d.transfers_in_progress.awaiting_approval, hint: `Choose the ${vocab.partner} who gives the ${vocab.items}`, href: "/transfers", icon: ArrowLeftRight },
                { label: `Invoice sold ${vocab.items}`, value: d.sales_awaiting_invoicing.qty, hint: "Create invoice records for Xero", href: "/invoices", icon: ReceiptText },
                { label: `${vocab.Partner} locations below agreed level`, value: shortLocations, hint: "Not yet covered by stock or orders", href: "/backorders", icon: Store },
                { label: `Stock checks waiting for the ${vocab.partner}`, value: checksWaiting, hint: `${vocab.Items} not found: re-check or invoice`, href: "/sales", icon: ClipboardCheck, urgent: checksWaiting > 0 },
                { label: `${vocab.Partners} on hold`, value: onHold, hint: "Accounts paused", href: "/resellers", icon: Building2 },
              ]} />
            </Section>
            <Section title={`Your ${vocab.partners} this month`} className="xl:col-span-3" description="Click a number to see the detail">
              <Card padded={false}>
                <DataTable mobile="cards" label={`Your ${vocab.partners} this month`} search={false} rows={resellers ? dealers : null} rowKey={(x) => x.id} pageSize={8}
                  empty={`No ${vocab.partners} yet`} emptyHint={`Create the first ${vocab.partner} account to start.`}
                  columns={[
                    { key: "n", mobile: "primary", header: vocab.Partner, cell: (x) => <Link className="link font-medium" href={`/resellers/${x.id}`}>{x.name}</Link> },
                    { key: "u", mobile: "field", mobileOrder: 1, header: "Sold", align: "right", cell: (x) => <Link className="link num" href={`/sales?reseller=${x.id}`}>{x.units}</Link> },
                    { key: "s", mobile: "field", mobileOrder: 2, header: "In stock", align: "right", cell: (x) => <Link className="link num" href={`/consignment`}>{x.stock}</Link> },
                    { key: "w", mobile: "field", mobileOrder: 3, header: "Waiting", align: "right", cell: (x) => x.waiting
                      ? <Link className="link num font-semibold text-warning" href={`/backorders?reseller=${x.id}`}>{x.waiting}</Link>
                      : <span className="num text-ink-muted">0</span> },
                  ]} />
              </Card>
            </Section>
          </div>

          <Section title="Needs attention" description={attention.length ? `${plural(attention.length, "item")} across your ${vocab.partners}` : undefined}>
            <AttentionList items={attention} emptyDescription={`No urgent ${vocab.partner} requests, stock shortages, transfer issues or invoicing backlog.`} />
          </Section>

          <Section title="Recent activity">
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Card title="Latest sales and requests" padded={false}>
                <ActivityList items={activity} emptyTitle={`No ${vocab.partner} activity yet`}
                  emptyDescription="Sales and replenishment requests will appear here as they are recorded." />
              </Card>
              <Card title="Transfers in progress" padded={false}
                actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/transfers">All transfers</Link>}>
                <DataTable mobile="cards" label="Transfers" search={false} rows={transfers} rowKey={(t) => t.id} pageSize={6}
                  empty="No transfers in progress" emptyHint={`${vocab.Items} moving between ${vocab.partners} appear here.`}
                  columns={[
                    { key: "n", mobile: "primary", header: "Transfer", cell: (t) => <Link className="link" href={`/transfers/${t.id}`}>{t.number}</Link> },
                    { key: "r", mobile: "field", mobileLabel: "Route", mobileOrder: 1, header: "From → To", cell: (t) => <FlowInline from={t.source_reseller_name ?? t.source_location_code ?? "Source pending"} to={t.destination_reseller_name ?? t.destination_location_code ?? "—"} /> },
                    { key: "q", mobile: "field", mobileOrder: 2, header: "Qty", align: "right", cell: (t) => t.quantity },
                    { key: "st", mobile: "status", header: "Status", cell: (t) => <Badge value={t.status} /> },
                  ]} />
              </Card>
            </div>
          </Section>
        </>
      )}
    </>
  );
}

function buildAttention(d: Dashboard | null, positions: AllocationPosition[] | null): AttentionItem[] {
  if (!d) return [];
  const out: AttentionItem[] = [];
  const t = d.transfers_in_progress;
  const items = d.replenishment_attention.items;
  const urgent = items.filter((i) => i.priority === "URGENT" || i.priority === "HIGH");
  const today = todayIso();
  const overdue = items.filter((i) => !urgent.includes(i) && ((i.expected_date && i.expected_date < today) || i.age_days >= uiConfig.backorderOverdueDays));
  if (t.discrepancies) out.push({ key: "disc", tone: "danger", icon: CircleAlert, href: "/transfers", title: plural(t.discrepancies, "transfer discrepancy", "transfer discrepancies"), detail: "Collected stock was not fully received" });
  if (urgent.length) out.push({ key: "urgent", tone: "danger", icon: TriangleAlert, href: urgent.length === 1 ? `/replenishment/${urgent[0].request_id}` : "/backorders", title: plural(urgent.length, `urgent ${vocab.partner} request`), detail: `${urgent[0].number} · ${urgent[0].qty_awaiting_supply} unit(s) awaiting${urgent[0].expected_date ? ` · expected ${fmtDate(urgent[0].expected_date)}` : ""}` });
  if (overdue.length) out.push({ key: "overdue", tone: "warn", icon: Clock, href: "/backorders", title: plural(overdue.length, "overdue backorder"), detail: `Past the expected date or older than ${uiConfig.backorderOverdueDays} days` });
  const short = (positions ?? []).filter((p) => p.remaining_unmet > 0);
  if (short.length) out.push({ key: "short", tone: "warn", icon: Store, href: "/consignment", title: `${plural(new Set(short.map((p) => p.location_id)).size, "location")} below target`, detail: `${short.reduce((a, p) => a + p.remaining_unmet, 0)} unit(s) of target not covered by stock or open demand` });
  return out;
}
