"use client";

import { FilePlus2, Hourglass, Package, PackageCheck, ShoppingCart, Store } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AllocationPosition, Dashboard, Delivery, ReplenishmentRequest, Sale } from "@/lib/types";
import { StockOrigin } from "../StockOrigin";
import { Alert, Badge, ButtonLink, Card, DataTable, Loading, ProductCell, Qty } from "../ui";
import { ActivityList, DashboardHeader, JobList, plural, RoleBanner, Section, thisMonth, type ActivityItem } from "./shared";
import { CallMeButton } from "../fulfilment/CallMeButton";
import { DealerMessages } from "./DealerMessages";
import { StockCheckAlerts } from "./StockCheckAlerts";
import { StockRequestsPanel } from "./StockRequestsPanel";
import { TyreLabel } from "../pickers";
import { vocab } from "@/lib/terms";

interface HistoryRow { occurred_at: string; transaction_number: string; category: string; sku: string; qty_in: number; qty_out: number; reference_number: string | null }

/** "What stock do I currently have and what am I waiting for?" — deliberately simple. */
export function ResellerDashboard() {
  const { user, can } = useAuth();
  const rid = user?.reseller_id ?? null;
  const { data: d, error } = useApi<Dashboard>("/reports/dashboard");
  const { data: positions } = useApi<AllocationPosition[]>(rid ? "/allocations/positions" : null, { reseller_id: rid ?? undefined });
  const { data: requests } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { open_only: true });
  const { data: deliveries } = useApi<Delivery[]>("/replenishment/deliveries", { open_only: true });
  const { data: sales } = useApi<Sale[]>("/sales");
  const { data: history } = useApi<{ rows: HistoryRow[] }>(rid ? `/reports/resellers/${rid}/transactions` : null);

  const attentionRows = useMemo(() => (positions ?? []).filter((p) => p.available === 0 || p.on_hand < p.target_qty), [positions]);
  const activity = useMemo<ActivityItem[] | null>(() => history
    ? [...history.rows].reverse().slice(0, 8).map((r, i) => ({ key: `${r.transaction_number}-${i}`, icon: r.qty_in ? Package : ShoppingCart, at: r.occurred_at,
      title: <>{humanize(r.category)} · <TyreLabel sku={r.sku} /></>, detail: `${r.qty_in ? `+${r.qty_in}` : `−${r.qty_out}`} unit(s)${r.reference_number ? ` · ${r.reference_number}` : ""}` }))
    : null, [history]);

  if (!user) return null;
  const outstanding = (requests ?? []).reduce((a, r) => a + r.qty_outstanding, 0);
  const inTransit = (deliveries ?? []).filter((x) => x.status === "IN_TRANSIT");
  const unitsOnTheWay = inTransit.reduce((a, x) => a + x.lines.reduce((b, l) => b + l.qty_dispatched, 0), 0);

  const month = thisMonth(sales);
  const soldUnits = month.reduce((a, x) => a + x.total_qty, 0);
  const low = attentionRows.length;

  return (
    <>
      <DashboardHeader name={user.full_name} subtitle={`Your ${vocab.site}: what you have, what is on the way and what to do next.`}
        actions={<>
          {can("stock_request.create") && <ButtonLink href="/stock-requests/new"><FilePlus2 aria-hidden />Request stock</ButtonLink>}
          {can("sales.record") && <ButtonLink href="/sales?new=1" variant="primary"><ShoppingCart aria-hidden />Report a sale</ButtonLink>}
        </>} />
      <Alert>{error}</Alert>
      <StockCheckAlerts />
      {!d && !error && <Loading label="Loading your account…" />}
      {d && (
        <>
          <RoleBanner theme="dealer" figures={[
            { label: `In my ${vocab.site}`, value: d.consignment.on_hand.toLocaleString(), href: "/consignment",
              hint: d.consignment.on_hand ? `${d.consignment.available.toLocaleString()} ready to sell` : "No stock placed with you yet" },
            { label: "On the way", value: unitsOnTheWay.toLocaleString(), href: "/replenishment?tab=deliveries",
              hint: plural(inTransit.length, "delivery", "deliveries") },
            { label: "Waiting for supply", value: d.backorders.qty_awaiting_supply.toLocaleString(), href: "/backorders",
              hint: `${plural((requests ?? []).length, "open request")} · ${outstanding} requested`, tone: d.backorders.qty_awaiting_supply ? "warn" : undefined },
            { label: "Sold this month", value: soldUnits.toLocaleString(), href: "/sales", hint: plural(month.length, "sale") },
          ]} />

          <DealerMessages actions={(n) => n.entity_type === "stock_request" && n.entity_id
            ? <CallMeButton requestId={n.entity_id} number={n.title.replace("Update on your order ", "")} /> : null} />
          <Section title="What to do next" className="mt-0" description="Each line opens the screen to do it">
            <JobList jobs={[
              { label: "Confirm deliveries that arrived", value: inTransit.length, hint: inTransit.length ? `${unitsOnTheWay} ${vocab.item}(s) on the way to you` : "Nothing on the way", href: "/replenishment?tab=deliveries", icon: PackageCheck, urgent: inTransit.length > 0 },
              { label: `Ask for ${vocab.items} running low`, value: low, hint: "Below your agreed level or nothing left to sell", href: "/stock-requests/new", icon: FilePlus2 },
              { label: "Check on waiting orders", value: (requests ?? []).length, hint: `${d.backorders.qty_awaiting_supply} ${vocab.item}(s) waiting for supply`, href: "/backorders", icon: Hourglass },
              { label: "Report today's sales", value: soldUnits, hint: `${vocab.Items} reported this month; report each sale so stock is replaced`, href: "/sales?new=1", icon: Store },
            ]} />
          </Section>

          <div className="mt-8"><StockRequestsPanel focus="request" /></div>

          <Section title="My stock requiring attention" description="Below your agreed level or with nothing left to sell">
            <Card padded={false}>
              <DataTable mobile="cards" label="My stock" search={false} rows={positions ? attentionRows : null} rowKey={(p) => `${p.location_id}-${p.product_id}`} pageSize={8}
                empty="Your stock is at its agreed levels" emptyHint={`${vocab.Items} that run low appear here, with anything already on the way.`}
                columns={[
                  { key: "p", mobile: "primary", header: vocab.Item, cell: (p) => <div className="flex items-center gap-1"><ProductCell name={p.product_name} sku={p.sku} /><StockOrigin locationId={p.location_id} productId={p.product_id} /></div> },
                  { key: "oh", mobile: "field", mobileOrder: 1, header: "In stock", align: "right", cell: (p) => <Qty value={p.on_hand} zeroMuted={false} tone={p.available === 0 ? "danger" : undefined} /> },
                  { key: "t", mobile: "field", mobileOrder: 2, header: "Agreed level", align: "right", cell: (p) => p.target_qty },
                  { key: "in", mobile: "field", mobileOrder: 3, header: "On the way", align: "right", cell: (p) => <Qty value={p.replenishment_in_transit + p.transfers_inbound} /> },
                  { key: "or", header: "Requested", align: "right", cell: (p) => <Qty value={p.open_replenishment} /> },
                ]} />
            </Card>
          </Section>

          <div className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card title="Recent sales reported" padded={false} actions={can("sales.record") && <Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/sales">Report a sale</Link>}>
              <DataTable search={false} rows={sales?.slice(0, 6)} rowKey={(s) => s.id}
                empty="No sales reported yet" emptyHint="Report each sale so replacement stock can be sent."
                columns={[
                  { key: "n", header: "Sale", cell: (s) => <Link className="link" href={`/sales?sale=${s.id}`}>{s.number}</Link> },
                  { key: "d", header: "Date", cell: (s) => <span className="text-ink-secondary">{fmtDate(s.sale_date)}</span> },
                  { key: "q", header: "Units", align: "right", cell: (s) => s.total_qty },
                ]} />
            </Card>
            <Card title="Deliveries in progress" padded={false}>
              <DataTable mobile="cards" label="Deliveries" search={false} rows={deliveries} rowKey={(x) => x.id}
                empty="No deliveries on the way" emptyHint="Dispatched replacement stock will appear here until it arrives."
                columns={[
                  { key: "n", mobile: "primary", header: "Delivery", cell: (x) => <span className="font-medium">{x.number}</span> },
                  { key: "d", mobile: "field", mobileOrder: 1, header: "Dispatched", cell: (x) => <span className="text-ink-secondary">{fmtDateTime(x.dispatched_at)}</span> },
                  { key: "q", mobile: "field", mobileOrder: 2, header: "Units", align: "right", cell: (x) => x.lines.reduce((a, l) => a + l.qty_dispatched, 0) },
                  { key: "s", mobile: "status", header: "Status", cell: (x) => <Badge value={x.status} /> },
                ]} />
            </Card>
          </div>

          <Section title="Recent activity">
            <Card padded={false}>
              <ActivityList items={activity} emptyTitle="No activity yet" emptyDescription="Deliveries, sales and stock movements on your account will appear here." />
            </Card>
          </Section>
        </>
      )}
    </>
  );
}
