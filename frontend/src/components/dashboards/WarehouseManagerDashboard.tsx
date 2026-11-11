"use client";

import {
  ArrowLeftRight, FileSpreadsheet, CircleAlert, ClipboardCheck, ClipboardList, HeartHandshake, PackageCheck, PackagePlus, PackageX, Truck,
  TriangleAlert, Warehouse,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { uiConfig } from "@/config/branding";
import { useAuth } from "@/lib/auth";
import { fmtDate, todayIso } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Dashboard, Delivery, PickRow, PurchaseOrder, ReplenishmentRequest, StockRequestSummary, Transfer } from "@/lib/types";
import { CheckStockButton } from "../CheckStock";
import { EXPORT_URL } from "../ProductImport";
import { links, NumLink } from "../NumLink";
import { Alert, Badge, buttonClass, ButtonLink, Card, DataTable, Loading, ProductCell, Qty } from "../ui";
import { AttentionList, DashboardHeader, JobList, plural, RoleBanner, Section, type AttentionItem } from "./shared";
import { StockCheckAlerts } from "./StockCheckAlerts";
import { StockCheckSchedule } from "../StockCheckSchedule";
import { vocab } from "@/lib/terms";

interface AvailRow { product_id: number; sku: string; product_name: string; on_hand: number; reserved: number; blocked: number;
  available: number; incoming: number; awaiting_supply_demand: number }

/** "What does the warehouse need to do today?" */
export function WarehouseManagerDashboard() {
  const { user, can } = useAuth();
  const { data: d, error } = useApi<Dashboard>("/reports/dashboard");
  const { data: avail } = useApi<AvailRow[]>("/reports/warehouse-availability");
  const { data: picks } = useApi<PickRow[]>(can("replenishment.dispatch") ? "/replenishment/pick-list" : null);
  const { data: pos } = useApi<PurchaseOrder[]>("/purchasing/purchase-orders", { open_only: true });
  const { data: transfers } = useApi<Transfer[]>("/transfers", { open_only: true });
  const { data: deliveries } = useApi<Delivery[]>("/replenishment/deliveries", { open_only: true });
  const { data: requests } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { backorders_only: true });
  const { data: srs } = useApi<StockRequestSummary>("/stock-requests/summary");

  const today = todayIso();
  const sums = useMemo(() => (avail ?? []).reduce((a, r) => ({ incoming: a.incoming + r.incoming, blocked: a.blocked + r.blocked }), { incoming: 0, blocked: 0 }), [avail]);
  const pickUnits = (picks ?? []).reduce((a, r) => a + r.open_qty, 0);
  const pickDest = new Set((picks ?? []).map((r) => r.location_id)).size;
  const openPOs = useMemo(() => pos ?? [], [pos]);
  const poUnits = openPOs.reduce((a, p) => a + p.lines.reduce((b, l) => b + l.qty_outstanding, 0), 0);
  const collections = (transfers ?? []).filter((t) => t.status === "APPROVED");
  const toFind = (transfers ?? []).filter((t) => t.status === "REQUESTED");
  const latePOs = openPOs.filter((p) => p.expected_date && p.expected_date < today);
  const inTransitTransfers = (transfers ?? []).filter((t) => t.status === "IN_TRANSIT");
  // Via-warehouse transfers on their way in: received and checked here before the rep delivers them.
  const toCheck = inTransitTransfers.filter((t) => t.route === "VIA_WAREHOUSE" && !t.warehouse_received_at);
  const deliveriesInTransit = (deliveries ?? []).filter((x) => x.status === "IN_TRANSIT");

  const attention = useMemo<AttentionItem[]>(() => {
    const out: AttentionItem[] = [];
    const oos = (avail ?? []).filter((r) => r.available === 0 && r.awaiting_supply_demand > 0);
    if (oos.length) out.push({ key: "oos", tone: "danger", icon: PackageX, href: "/warehouse", title: plural(oos.length, "SKU out of stock with demand", "SKUs out of stock with demand"), detail: oos.slice(0, 3).map((r) => `${r.product_name ?? ""} (${r.sku})`).join(", ") + (oos.length > 3 ? ` +${oos.length - 3} more` : "") });
    const urgent = (requests ?? []).filter((r) => (r.priority === "URGENT" || r.priority === "HIGH") && r.qty_awaiting_supply > 0);
    if (urgent.length) out.push({ key: "urgent", tone: "danger", icon: TriangleAlert, href: "/backorders", title: plural(urgent.length, "urgent backorder"), detail: `${urgent.reduce((a, r) => a + r.qty_awaiting_supply, 0)} unit(s) awaiting stock` });
    const late = openPOs.filter((p) => p.expected_date && p.expected_date < today);
    if (late.length) out.push({ key: "late", tone: "warn", icon: Truck, href: "/purchasing", title: plural(late.length, "shipment overdue", "shipments overdue"), detail: late.slice(0, 2).map((p) => `${p.number} (${p.supplier_name}, due ${fmtDate(p.expected_date)})`).join(" · ") });
    const disc = (transfers ?? []).filter((t) => t.status === "RECEIVED_WITH_DISCREPANCY").length
      + (deliveries ?? []).filter((x) => x.status === "RECEIVED_WITH_DISCREPANCY").length;
    if (disc) out.push({ key: "disc", tone: "danger", icon: CircleAlert, href: "/replenishment?tab=deliveries", title: plural(disc, "stock discrepancy", "stock discrepancies"), detail: "Dispatched or collected stock not fully received — resolve to keep balances accurate" });
    const low = (avail ?? []).filter((r) => r.available > 0 && r.available <= uiConfig.lowStockThreshold);
    if (low.length) out.push({ key: "low", tone: "warn", icon: Warehouse, href: "/warehouse", title: plural(low.length, "SKU low in stock", "SKUs low in stock"), detail: `${uiConfig.lowStockThreshold} or fewer units available` });
    if (sums.blocked) out.push({ key: "blocked", tone: "warn", icon: PackageX, href: "/warehouse", title: `${plural(sums.blocked, "unit")} blocked`, detail: "Damaged or quarantined — release or write off" });
    return out;
  }, [avail, requests, openPOs, transfers, deliveries, sums.blocked, today]);

  if (!user) return null;

  return (
    <>
      <DashboardHeader name={user.full_name} subtitle={`Today's jobs in the warehouse: approve, pick and ship, find ${vocab.items} from ${vocab.partners}, receive supplier stock.`}
        actions={<>
          {can("transfer.request") && <CheckStockButton />}
          {can("catalogue.import") && <a href={EXPORT_URL} download title="Edit or add rows, then use Import from Excel."
            className={buttonClass()}>
            <FileSpreadsheet className="size-4" aria-hidden />Export SKUs</a>}
          {can("inventory.receive") && <ButtonLink href="/purchasing"><PackagePlus aria-hidden />Receive goods</ButtonLink>}
          {can("replenishment.dispatch") && <ButtonLink href="/replenishment" variant="primary"><Truck aria-hidden />Pick &amp; dispatch</ButtonLink>}
        </>} />
      <Alert>{error}</Alert>
      {!d && !error && <Loading label="Loading dashboard…" />}
      {d?.warehouse && (
        <>
          <RoleBanner theme="warehouse" figures={[
            { label: "On hand", value: d.warehouse.on_hand.toLocaleString(), href: "/warehouse", hint: avail ? `${avail.length} SKUs` : undefined },
            { label: "Available", value: d.warehouse.available.toLocaleString(), href: "/warehouse", hint: "Free to approve or ship" },
            { label: "Reserved", value: d.warehouse.reserved.toLocaleString(), href: links.reserved(), hint: "Approved, waiting to ship" },
            { label: "Blocked", value: sums.blocked.toLocaleString(), href: links.movements(), hint: "Damaged or quarantined", tone: sums.blocked ? "warn" : undefined },
            { label: "Incoming", value: sums.incoming.toLocaleString(), href: links.incoming(), hint: "On open purchase orders" },
          ]} />
          <StockCheckAlerts />
          <StockCheckSchedule title={`Stock checks due at ${vocab.partners}`} canRecord={can("stocktake.record")} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
            <Section title="Today's jobs" className="xl:col-span-3" description="Work top to bottom; each line opens the screen to do it">
              <JobList jobs={[
                { label: "Approve stock requests", value: srs?.pending_approval ?? 0, hint: `${vocab.Partners} waiting for a decision`, href: "/stock-requests/pending", icon: ClipboardCheck },
                { label: "Pick, pack and ship", value: pickUnits + (srs?.to_ship ?? 0), hint: `${plural(pickUnits, "unit")} to dispatch to ${plural(pickDest, vocab.partner, vocab.partners)} · ${plural(srs?.to_ship ?? 0, "approved request")} to ship`, href: "/replenishment", icon: PackageCheck },
                { label: `Find ${vocab.items} from other ${vocab.partners}`, value: toFind.length, hint: `\"Get this ${vocab.item} for me\" and other transfer requests`, href: "/transfers", icon: HeartHandshake, urgent: toFind.length > 0 },
                { label: "Collect transfers", value: collections.length, hint: `${inTransitTransfers.length} already on the way`, href: "/transfers", icon: ArrowLeftRight },
                { label: "Check transfers at the warehouse", value: toCheck.length, hint: `Collected from ${vocab.aPartner}, to be received and checked here`, href: "/transfers", icon: ArrowLeftRight, urgent: toCheck.length > 0 },
                { label: "Receive supplier deliveries", value: openPOs.length, hint: latePOs.length ? `${plural(latePOs.length, "order")} overdue · ${poUnits} units outstanding` : `${poUnits} units outstanding`, href: "/purchasing", icon: ClipboardList, urgent: latePOs.length > 0 },
                { label: "Deliveries on the road", value: deliveriesInTransit.length, hint: `Waiting for the ${vocab.partner} to confirm`, href: "/replenishment?tab=deliveries", icon: Truck },
              ]} />
            </Section>
            <Section title="Attention" className="xl:col-span-2" description="Problems to sort out">
              <AttentionList items={attention} emptyDescription="No stock-outs with demand, urgent backorders, late shipments or discrepancies." />
            </Section>
          </div>

          <Section title="Supply and demand">
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Card title={`Out of stock with ${vocab.partners} waiting`} subtitle="Order or arrange these first" padded={false}
                actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/backorders">Backorders</Link>}>
                <DataTable mobile="cards" label={`${vocab.Items} in demand`} search={false} pageSize={6} rowKey={(r) => r.product_id}
                  rows={avail ? avail.filter((r) => r.awaiting_supply_demand > r.available).sort((a, b) => b.awaiting_supply_demand - a.awaiting_supply_demand) : null}
                  empty="Every demand can be supplied" emptyHint={`${vocab.Items} with more demand than warehouse stock appear here.`}
                  columns={[
                    { key: "p", mobile: "primary", header: vocab.Item, cell: (r) => <ProductCell name={r.product_name} sku={r.sku} /> },
                    { key: "a", mobile: "field", mobileOrder: 1, header: "Available", align: "right", cell: (r) => <NumLink href={links.whereIs(r.product_id)} title="Where is it?"><Qty value={r.available} zeroMuted={false} tone={r.available ? undefined : "danger"} /></NumLink> },
                    { key: "d", mobile: "field", mobileOrder: 2, header: "Waiting", align: "right", cell: (r) => <NumLink href={links.demand(r.product_id)} title="Who is waiting"><Qty value={r.awaiting_supply_demand} tone="warn" /></NumLink> },
                    { key: "i", mobile: "field", mobileOrder: 3, header: "Incoming", align: "right", cell: (r) => <NumLink href={r.incoming ? links.incoming(r.sku) : null}><Qty value={r.incoming} /></NumLink> },
                  ]} />
              </Card>
              <Card title="Expected supplier deliveries" subtitle="Open purchase orders" padded={false}
                actions={<Link className="text-label font-medium text-ink-secondary hover:text-ink" href="/purchasing">Purchasing</Link>}>
                <DataTable mobile="cards" label="Supplier orders" search={false} rows={pos} rowKey={(p) => p.id} pageSize={6}
                  empty="No shipments expected" emptyHint="Create a purchase order to track incoming supplier stock."
                  columns={[
                    { key: "n", mobile: "primary", header: "Order", cell: (p) => <Link className="link" href={`/purchasing?q=${encodeURIComponent(p.number)}`}><div className="font-medium">{p.number}</div><div className="text-caption text-ink-muted">{p.supplier_name}</div></Link> },
                    { key: "e", mobile: "field", mobileOrder: 1, header: "Expected", cell: (p) => <span className={p.expected_date && p.expected_date < today ? "font-medium text-danger" : "text-ink-secondary"}>{fmtDate(p.expected_date)}</span> },
                    { key: "q", mobile: "field", mobileOrder: 2, header: "Outstanding", align: "right", cell: (p) => p.lines.reduce((a, l) => a + l.qty_outstanding, 0) },
                    { key: "s", mobile: "status", header: "Status", cell: (p) => <Badge value={p.status} /> },
                  ]} />
              </Card>
            </div>
          </Section>
        </>
      )}
    </>
  );
}
