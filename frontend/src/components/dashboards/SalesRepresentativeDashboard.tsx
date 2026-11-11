"use client";

import { ArrowLeftRight, ClipboardCheck, Hourglass, Inbox, RefreshCw, ShoppingCart, Store, Truck } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { fmtDate, todayIso } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AllocationPosition, Delivery, ReplenishmentRequest, ResellerSummary, Sale, Stocktake, Transfer } from "@/lib/types";
import { CheckStockButton } from "../CheckStock";
import { FlowInline } from "../flow";
import { links, NumLink } from "../NumLink";
import { Alert, Badge, ButtonLink, Card, DataTable, Loading, Qty } from "../ui";
import {
  ActivityList, AttentionList, DashboardHeader, JobList, plural, RoleBanner, Section, thisMonth, type ActivityItem,
  type AttentionItem,
} from "./shared";
import { StockCheckAlerts } from "./StockCheckAlerts";
import { StockCheckSchedule, useStockCheckSchedule } from "../StockCheckSchedule";

/** Customers without a stocktake in this many days are shown as "stocktake due". */
const STOCKTAKE_DUE_DAYS = 30;

/** "My Customers & Actions" for a sales representative visiting reseller sites. */
export function SalesRepresentativeDashboard() {
  const { user, can } = useAuth();
  const { data: resellers, error } = useApi<ResellerSummary[]>("/resellers");
  const { data: stocktakes } = useApi<Stocktake[]>("/stocktakes");
  const { data: positions } = useApi<AllocationPosition[]>("/allocations/positions");
  const { data: requests } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { open_only: true });
  const { data: transfers } = useApi<Transfer[]>("/transfers", { open_only: true });
  const { data: sales } = useApi<Sale[]>("/sales");
  const { data: deliveries } = useApi<Delivery[]>("/replenishment/deliveries");

  // Customers assigned to this rep; when none are assigned yet, every active reseller the rep may see.
  const assigned = useMemo(() => (resellers ?? []).filter((r) => r.sales_rep_user_id === user?.id), [resellers, user]);
  const customers = useMemo(() => (assigned.length ? assigned : (resellers ?? []).filter((r) => r.status !== "CLOSED")), [assigned, resellers]);
  const mine = useMemo(() => new Set(customers.map((c) => c.id)), [customers]);
  // Stock checks overdue or due today at this rep's dealers (the schedule allows for checks moved to another day).
  const { data: checks } = useStockCheckSchedule();
  const dueChecks = (checks ?? []).filter((r) => (!assigned.length || r.sales_rep_user_id === user?.id) && (r.status === "OVERDUE" || r.status === "DUE"));

  const view = useMemo(() => {
    const cutoff = new Date(new Date(`${todayIso()}T00:00:00Z`).getTime() - STOCKTAKE_DUE_DAYS * 864e5).toISOString().slice(0, 10);
    const lastCount = new Map<number, string>();
    (stocktakes ?? []).forEach((s) => { if (mine.has(s.reseller_id) && (!lastCount.get(s.reseller_id) || s.count_date > lastCount.get(s.reseller_id)!)) lastCount.set(s.reseller_id, s.count_date); });
    const due = customers.filter((c) => c.status === "ACTIVE" && (!lastCount.get(c.id) || lastCount.get(c.id)! < cutoff));
    const short = (positions ?? []).filter((p) => mine.has(p.reseller_id) && p.remaining_unmet > 0);
    const backorders = (requests ?? []).filter((r) => mine.has(r.reseller_id) && r.qty_awaiting_supply > 0);
    const myTransfers = (transfers ?? []).filter((t) => (t.destination_reseller_id && mine.has(t.destination_reseller_id)) || (t.source_reseller_id && mine.has(t.source_reseller_id)));
    const requested = myTransfers.filter((t) => t.status === "REQUESTED");
    const stock = new Map<number, number>();
    (positions ?? []).forEach((p) => stock.set(p.reseller_id, (stock.get(p.reseller_id) ?? 0) + p.on_hand));
    const soldMonth = new Map<number, number>();
    thisMonth(sales).forEach((x) => { if (mine.has(x.reseller_id)) soldMonth.set(x.reseller_id, (soldMonth.get(x.reseller_id) ?? 0) + x.total_qty); });
    // Hand-overs: warehouse deliveries in this rep's vehicle, and transfers they carry between dealers — both the
    // ones still to collect and the ones to deliver (finding 23).
    const carriesTransfer = (t: Transfer) => t.carried_by_user_id === user?.id || (!t.carried_by_user_id && t.collected_by_user_id === user?.id);
    const carrying = [
      ...(deliveries ?? []).filter((x) => x.status === "IN_TRANSIT" && x.carried_by_user_id === user?.id)
        .map((x) => ({ key: `d${x.id}`, href: links.deliveries(), number: x.number, from: "You", to: x.reseller_name ?? "", kind: "Delivery · to deliver" })),
      ...(transfers ?? []).filter((t) => t.status === "APPROVED" && t.carried_by_user_id === user?.id)
        .map((t) => ({ key: `tc${t.id}`, href: `/transfers/${t.id}`, number: t.number, from: t.source_reseller_name ?? t.source_location_code ?? "—",
          to: t.destination_reseller_name ?? t.destination_location_code ?? "", kind: "Transfer · to collect" })),
      // Via the warehouse: take it there to be checked first, then deliver it (UAT round 2).
      ...(transfers ?? []).filter((t) => t.status === "IN_TRANSIT" && carriesTransfer(t))
        .map((t) => (t.route === "VIA_WAREHOUSE" && !t.warehouse_received_at
          ? { key: `t${t.id}`, href: `/transfers/${t.id}`, number: t.number, from: "You", to: "The warehouse", kind: "Transfer · to the warehouse" }
          : { key: `t${t.id}`, href: `/transfers/${t.id}`, number: t.number, from: "You", to: t.destination_reseller_name ?? t.destination_location_code ?? "", kind: "Transfer · to deliver" })),
    ];
    return { lastCount, due, short, backorders, myTransfers, requested, stock, soldMonth, carrying };
  }, [customers, mine, stocktakes, positions, requests, transfers, sales, deliveries, user]);

  const attention = useMemo<AttentionItem[]>(() => {
    const out: AttentionItem[] = [];
    const shortLocs = new Set(view.short.map((p) => p.location_id)).size;
    if (shortLocs) out.push({ key: "short", tone: "warn", icon: Store, href: "/consignment", title: `${plural(shortLocs, "customer location")} low on consignment stock`, detail: `${view.short.reduce((a, p) => a + p.remaining_unmet, 0)} unit(s) below target and not yet requested` });
    if (view.backorders.length) out.push({ key: "back", tone: "warn", icon: Hourglass, href: "/backorders", title: plural(view.backorders.length, "outstanding customer backorder"), detail: `${view.backorders.reduce((a, r) => a + r.qty_awaiting_supply, 0)} unit(s) awaiting supply` });
    if (view.requested.length) out.push({ key: "tr", tone: "info", icon: ArrowLeftRight, href: "/transfers", title: plural(view.requested.length, "pending transfer request"), detail: "Waiting for dealership approval" });
    return out;
  }, [view]);

  const activity = useMemo<ActivityItem[] | null>(() => {
    if (!stocktakes || !sales || !requests) return null;
    return [
      ...stocktakes.filter((s) => mine.has(s.reseller_id)).map((s) => ({ key: `st${s.id}`, icon: ClipboardCheck, at: s.submitted_at ?? `${s.count_date}T00:00:00`, href: `/stocktakes/${s.id}`,
        title: <>Stocktake <b className="font-medium">{s.number}</b> · {s.reseller_name}</>, detail: `${s.status.toLowerCase().replace("_", " ")} · variance ${s.total_variance}` })),
      ...sales.filter((s) => mine.has(s.reseller_id)).map((s) => ({ key: `s${s.id}`, icon: ShoppingCart, at: s.recorded_at, href: `/sales?sale=${s.id}`,
        title: <>Sale reported <b className="font-medium">{s.number}</b> · {s.reseller_name}</>, detail: `${s.total_qty} unit(s)` })),
      ...requests.filter((r) => mine.has(r.reseller_id)).map((r) => ({ key: `r${r.id}`, icon: RefreshCw, at: r.created_at, href: `/replenishment/${r.id}`,
        title: <>Replenishment submitted <b className="font-medium">{r.number}</b> · {r.reseller_name}</>, detail: `${r.qty_required} × ${r.product_name} (${r.sku})` })),
    ].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 8);
  }, [stocktakes, sales, requests, mine]);

  if (!user) return null;

  const waitingUnits = view.backorders.reduce((a, r) => a + r.qty_awaiting_supply, 0);
  const shortLocs = new Set(view.short.map((p) => p.location_id)).size;
  const soldUnits = [...view.soldMonth.values()].reduce((a, n) => a + n, 0);

  return (
    <>
      <DashboardHeader name={user.full_name}
        subtitle={assigned.length ? `Your day on the road: ${plural(assigned.length, "dealer")} assigned to you.` : "Your day on the road: stock checks, sales, hand-overs and requests for your dealers."}
        actions={<>
          {can("transfer.request") && <CheckStockButton />}
          {can("sales.record") && <ButtonLink href="/sales?new=1"><ShoppingCart aria-hidden />Record sale</ButtonLink>}
          {can("stocktake.record") && <ButtonLink href="/stocktakes/new" variant="primary"><ClipboardCheck aria-hidden />Start stock check</ButtonLink>}
        </>} />
      <Alert>{error}</Alert>
      {!resellers && !error && <Loading label="Loading your dealers…" />}
      {resellers && (
        <>
          {resellers.length > 0 && !assigned.length && (
            <Alert tone="info">No dealers are assigned to you yet, so all active dealers are shown. The Relationship Manager can assign you on each dealer’s profile.</Alert>
          )}
          <RoleBanner theme="field" figures={[
            { label: "My dealers", value: customers.length, href: "/resellers", hint: assigned.length ? "Assigned to you" : "All active dealers" },
            { label: "Stock checks due", value: dueChecks.length, href: "/sales", hint: `Overdue or due today (every ${STOCKTAKE_DUE_DAYS} days)`, tone: dueChecks.length ? "warn" : undefined },
            { label: "To hand over", value: view.carrying.length, href: links.deliveries(), hint: "Tyres you are carrying", tone: view.carrying.length ? "warn" : undefined },
            { label: "Sold this month", value: soldUnits, href: "/sales", hint: "Tyres at your dealers" },
            { label: "Waiting for supply", value: waitingUnits, href: "/backorders", hint: plural(view.backorders.length, "open request"), tone: waitingUnits ? "warn" : undefined },
          ]} />
          <StockCheckAlerts />
          <StockCheckSchedule title="My stock checks" repId={assigned.length ? user?.id : null} canRecord />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
            <Section title="Today's visits" className="xl:col-span-3" description="Each line opens the screen to do it">
              <JobList jobs={[
                { label: "Hand over tyres you are carrying", value: view.carrying.length, hint: "Dealer confirms with name and notes", href: links.deliveries(), icon: Truck, urgent: view.carrying.length > 0 },
                { label: "Do stock checks", value: dueChecks.length, hint: "Shops overdue or due today; move one if it can't happen", href: "/stocktakes/new", icon: ClipboardCheck },
                { label: "Top up dealers below agreed level", value: shortLocs, hint: `${view.short.reduce((a, p) => a + p.remaining_unmet, 0)} tyre(s) short`, href: "/consignment", icon: RefreshCw },
                { label: "Transfers waiting for approval", value: view.requested.length, hint: "Tyres asked for between dealers", href: "/transfers", icon: Inbox },
                { label: "Follow up on waiting orders", value: view.backorders.length, hint: `${plural(waitingUnits, "tyre")} waiting for supply`, href: "/backorders", icon: Hourglass },
              ]} />
            </Section>
            <Section title="Hand-overs" className="xl:col-span-2" description="To collect, and in your vehicle now">
              <Card padded={false}>
                <DataTable search={false} pageSize={6} rowKey={(x) => x.key} rows={deliveries && transfers ? view.carrying : null}
                  empty="Nothing to hand over" emptyHint="Transfers you are asked to carry, and deliveries and transfers you collect, appear here until the dealer confirms."
                  columns={[
                    { key: "n", header: "What", cell: (x) => <Link className="link" href={x.href}><div className="font-medium">{x.number}</div><div className="text-caption text-ink-muted">{x.kind}</div></Link> },
                    { key: "t", header: "Route", cell: (x) => <FlowInline from={x.from} to={x.to || "—"} /> },
                  ]} />
              </Card>
            </Section>
          </div>

          <Section title="My dealers">
            <Card padded={false}>
              <DataTable mobile="cards" label="My dealers" rows={customers} rowKey={(c) => c.id} search={customers.length > 8} pageSize={10}
                empty="No dealer accounts yet" emptyHint="Dealer accounts appear here once the Relationship Manager creates them."
                columns={[
                  { key: "n", mobile: "primary", header: "Dealer", value: (c) => c.business_name, cell: (c) => <div><Link className="link" href={`/resellers/${c.id}`}>{c.business_name}</Link><div className="sku text-label text-ink-secondary">{c.account_ref}</div></div> },
                  { key: "st", mobile: "field", mobileOrder: 1, header: "Last stock check", value: (c) => view.lastCount.get(c.id) ?? "", cell: (c) => view.lastCount.get(c.id) ? <span className="text-ink-secondary">{fmtDate(view.lastCount.get(c.id))}</span> : <Badge value="ACTION_REQUIRED" label="Never" /> },
                  { key: "sm", mobile: "field", mobileOrder: 2, header: "Sold this month", align: "right", value: (c) => view.soldMonth.get(c.id) ?? 0, cell: (c) => <NumLink href={`/sales?reseller=${c.id}`}><Qty value={view.soldMonth.get(c.id) ?? 0} /></NumLink> },
                  { key: "oh", header: "In stock", align: "right", value: (c) => view.stock.get(c.id) ?? 0, cell: (c) => <NumLink href="/consignment"><Qty value={view.stock.get(c.id) ?? 0} /></NumLink> },
                  { key: "bo", mobile: "field", mobileOrder: 3, header: "Waiting", align: "right", cell: (c) => { const n = view.backorders.filter((r) => r.reseller_id === c.id).reduce((a, r) => a + r.qty_awaiting_supply, 0); return <NumLink href={n ? links.demand(null, c.id) : null}><Qty value={n} tone="warn" /></NumLink>; } },
                  { key: "s", mobile: "status", header: "Status", cell: (c) => <Badge value={c.status} /> },
                ]} />
            </Card>
          </Section>

          <Section title="Needs attention">
            <div className="grid grid-cols-1 gap-4 items-start xl:grid-cols-2">
              <AttentionList items={attention} emptyDescription="Your dealers have no shortfalls, waiting orders or pending transfers." />
              <Card title="Recent activity" padded={false}>
                <ActivityList items={activity} emptyTitle="No dealer activity yet" emptyDescription="Stock checks, reported sales and requests will appear here." />
              </Card>
            </div>
          </Section>
        </>
      )}
    </>
  );
}
