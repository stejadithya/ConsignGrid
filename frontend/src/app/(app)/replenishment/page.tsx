"use client";

import { PackageCheck, Truck, Wand2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { DeliveriesTable } from "@/components/DeliveryPanel";
import { FlowInline } from "@/components/flow";
import { ResellerSelect, ShopLabel } from "@/components/pickers";
import { ShippingMethodFields, shippingBody, shippingReady, type Shipping } from "@/components/Shipping";
import { RequestsTable } from "@/components/tables";
import { CheckStockButton } from "@/components/CheckStock";
import {
  Alert, Badge, Button, Card, cx, DataTable, EmptyState, FilterField, MetricStrip, MobileActionBar, PageHeader,
  ProductCell, QuickFilters, Select, Tabs,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayIso } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Delivery, PickRow, ReplenishmentRequest } from "@/lib/types";

export default function ReplenishmentPage() {
  const { can } = useAuth();
  const canDispatch = can("replenishment.dispatch");
  const params = useSearchParams();
  const initial = params.get("tab");
  const [tab, setTab] = useState(initial === "deliveries" || initial === "requests" ? initial : canDispatch ? "dispatch" : "requests");
  return (
    <>
      <PageHeader title="Replenishment" subtitle="Restore dealer stock from the warehouse. Replenishment moves stock only — it never creates an invoice."
        actions={can("transfer.request") && <CheckStockButton />} />
      <Tabs active={tab} onChange={setTab} tabs={[
        ...(canDispatch ? [{ id: "dispatch", label: "Pick & dispatch" }] : []),
        { id: "requests", label: "Requests" }, { id: "deliveries", label: "Deliveries" },
      ]} />
      {tab === "dispatch" && <DispatchTab />}
      {tab === "requests" && <RequestsTab />}
      {tab === "deliveries" && <DeliveriesTab />}
    </>
  );
}

function DispatchTab() {
  const { data, error, reload } = useApi<PickRow[]>("/replenishment/pick-list");
  const [ship, setShip] = useState<Shipping>({ method: "COURIER", carrier: "", repId: "" });
  const [done, setDone] = useState<string | null>(null);
  const action = useAction();
  const groups = useMemo(() => {
    const m = new Map<number, PickRow[]>();
    (data ?? []).forEach((r) => m.set(r.location_id, [...(m.get(r.location_id) ?? []), r]));
    return [...m.entries()];
  }, [data]);
  const units = (data ?? []).reduce((a, r) => a + r.open_qty, 0);

  async function dispatch(locationId: number, rows: PickRow[]) {
    const reqs = [...new Set(rows.map((r) => r.request_id))];
    const d = await action.run(() => api.post<Delivery>("/replenishment/deliveries", {
      to_location_id: locationId, ...shippingBody(ship), carrier_reference: ship.method === "COURIER" ? ship.carrier || null : null,
      lines: reqs.map((id) => ({ request_id: id })),
    }));
    if (d) { setDone(`Dispatched ${d.number} to ${d.to_location_code}: ${d.lines.reduce((a, l) => a + l.qty_dispatched, 0)} unit(s) now in transit.`); reload(); }
  }

  return (
    <>
      <Alert>{error ?? action.error}</Alert>
      <Alert tone="success">{done}</Alert>
      <div className="mb-5 flex flex-col gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-center gap-6">
          <div><div className="text-caption font-medium text-ink-muted">Ready to dispatch</div><div className="num text-metric-compact font-semibold">{units}</div></div>
          <div><div className="text-caption font-medium text-ink-muted">Destinations</div><div className="num text-metric-compact font-semibold">{groups.length}</div></div>
        </div>
        <div className="w-full sm:w-96"><ShippingMethodFields value={ship} onChange={setShip} carrierLabel="Carrier / run reference (optional)" carrierRequired={false} /></div>
      </div>
      {data && groups.length === 0 && (
        <Card><EmptyState icon={PackageCheck} title="Nothing to dispatch" description="No allocated stock is waiting to be picked. New allocations appear here automatically." /></Card>
      )}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {groups.map(([locId, rows]) => (
          <Card key={locId} padded={false} icon={Truck}
            title={<>{rows[0].reseller_name} <span className="font-normal text-ink-muted">· <ShopLabel inline code={rows[0].location_code} withDealer={false} /></span></>}
            subtitle={<FlowInline from="Warehouse" to={rows[0].reseller_name} />}
            actions={<Button size="sm" variant="primary" className={cx(groups.length === 1 && "max-lg:hidden")} disabled={action.busy || !shippingReady(ship, false)} onClick={() => dispatch(locId, rows)}>Dispatch {rows.reduce((a, r) => a + r.open_qty, 0)} unit(s)</Button>}>
            <DataTable mobile="cards" density="comfortable" label="To pick" search={false} rows={rows} rowKey={(r) => r.allocation_id} columns={[
              { key: "s", mobile: "primary", header: "Product", cell: (r) => <ProductCell name={r.product_name} sku={r.sku} /> },
              { key: "r", mobile: "secondary", header: "Request", cell: (r) => <span className="inline-flex items-center gap-1.5 text-ink-secondary">
                <Link className="link" href={`/replenishment/${r.request_id}`}>{r.request_number}</Link>
                {r.ready && <Badge value="READY_FOR_SHIPMENT" label="Ready" />}</span> },
              { key: "p", mobile: "status", header: "Priority", cell: (r) => <Badge value={r.priority} /> },
              { key: "q", mobile: "field", header: "Pick qty", align: "right", cell: (r) => <span className="num text-body-lg font-semibold">{r.open_qty}</span> },
            ]} />
          </Card>
        ))}
      </div>
      {/* One destination: its Dispatch button docks at the bottom on phones and tablets in portrait. With several, each
          destination keeps its own button on its card (there is no single next action). */}
      {groups.length === 1 && (
        <MobileActionBar desktop="hidden">
          <Button variant="primary" disabled={action.busy || !shippingReady(ship, false)} onClick={() => dispatch(groups[0][0], groups[0][1])}>
            <Truck aria-hidden />Dispatch {groups[0][1].reduce((a, r) => a + r.open_qty, 0)} unit(s)</Button>
        </MobileActionBar>
      )}
    </>
  );
}

type QF = "all" | "attention" | "urgent" | "awaiting" | "ready" | "transit";

const QF_TEST: Record<QF, (r: ReplenishmentRequest, today: string) => boolean> = {
  all: () => true,
  attention: (r, today) => r.qty_outstanding > 0 && (["URGENT", "HIGH"].includes(r.priority) || r.age_days > 7 || (!!r.expected_date && r.expected_date < today)),
  urgent: (r) => r.priority === "URGENT" || r.priority === "HIGH",
  awaiting: (r) => r.qty_awaiting_supply > 0,
  ready: (r) => r.qty_allocated > 0,
  transit: (r) => r.qty_in_transit > 0,
};

function RequestsTab() {
  const { can } = useAuth();
  const [status, setStatus] = useState("open");
  const [reseller, setReseller] = useState<number | "">("");
  const [qf, setQf] = useState<QF>("all");
  const { data, error, reload } = useApi<ReplenishmentRequest[]>("/replenishment/requests", { open_only: status === "open", reseller_id: reseller });
  const action = useAction();
  const [msg, setMsg] = useState<string | null>(null);
  const today = todayIso();
  const count = (k: QF) => (data ?? []).filter((r) => QF_TEST[k](r, today)).length;
  const rows = data?.filter((r) => QF_TEST[qf](r, today)) ?? null;
  const sum = (f: (r: ReplenishmentRequest) => number) => (data ?? []).reduce((a, r) => a + f(r), 0);

  return (
    <>
      {data && (
        <MetricStrip items={[
          { label: "Open requests", value: (data ?? []).filter((r) => r.qty_outstanding > 0).length },
          { label: "Awaiting stock", value: sum((r) => r.qty_awaiting_supply), tone: sum((r) => r.qty_awaiting_supply) ? "warn" : "ok", hint: "units" },
          { label: "Allocated", value: sum((r) => r.qty_allocated + r.qty_transfer_covered), hint: "units reserved" },
          { label: "In transit", value: sum((r) => r.qty_in_transit), hint: "units on the road" },
        ]} />
      )}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <QuickFilters value={qf} onChange={setQf} options={[
          { id: "all", label: "All", count: data?.length }, { id: "attention", label: "Needs attention", count: count("attention") },
          { id: "urgent", label: "Urgent", count: count("urgent") }, { id: "awaiting", label: "Awaiting stock", count: count("awaiting") },
          { id: "ready", label: "Ready to dispatch", count: count("ready") }, { id: "transit", label: "In transit", count: count("transit") },
        ]} />
        {can("replenishment.manage") && <Button size="sm" disabled={action.busy} onClick={async () => {
          const r = await action.run(() => api.post<ReplenishmentRequest[]>("/replenishment/generate-shortfalls", { reseller_id: reseller || null }));
          if (r) { setMsg(r.length ? `Created ${r.length} request(s) for uncovered target shortfalls.` : "All targets are already covered by stock or open demand."); reload(); }
        }}><Wand2 aria-hidden />Generate target shortfalls</Button>}
      </div>
      <Alert>{error ?? action.error}</Alert><Alert tone="info">{msg}</Alert>
      <Card padded={false}>
        <RequestsTable rows={rows} showReseller empty={qf === "all" ? "No replenishment requests" : "Nothing in this view"}
          filterCount={[status !== "open", reseller].filter(Boolean).length}
          onClearFilters={() => { setStatus("open"); setReseller(""); }}
          filters={<>
            <FilterField label="Status" className="w-40"><Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "open", label: "Open" }, { value: "all", label: "All (incl. closed)" }]} /></FilterField>
            <FilterField label="Dealer" className="w-64"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField>
          </>} />
      </Card>
    </>
  );
}

function DeliveriesTab() {
  const q = useSearchParams().get("q") ?? "";   // opened from the search box: show that delivery, open or not
  const [openOnly, setOpenOnly] = useState(q ? "false" : "true");
  const { data, reload } = useApi<Delivery[]>("/replenishment/deliveries", { open_only: openOnly === "true" });
  return (
    <Card padded={false} title="Deliveries" subtitle="Warehouse dispatches to dealer locations"
      actions={<div className="w-64"><Select aria-label="Filter" value={openOnly} onChange={(e) => setOpenOnly(e.target.value)} options={[{ value: "true", label: "Open (in transit / discrepancy)" }, { value: "false", label: "All" }]} /></div>}>
      <DeliveriesTable rows={data} onChanged={reload} initialSearch={q} />
    </Card>
  );
}
