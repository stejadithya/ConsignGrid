"use client";

import { PackagePlus, Truck } from "lucide-react";
import { useMemo, useState } from "react";
import { LedgerTable } from "@/components/Ledger";
import { LocationSelect, ProductSelect, useLocations } from "@/components/pickers";
import { StockActions } from "@/components/StockActions";
import { links, NumLink } from "@/components/NumLink";
import { StockOrigin } from "@/components/StockOrigin";
import {
  Alert, Badge, Button, ButtonLink, Card, DataTable, Field, Input, MetricStrip, PageHeader, ProductCell, Qty, QuickFilters, Tabs, Textarea,
} from "@/components/ui";
import { uiConfig } from "@/config/branding";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useApi } from "@/lib/hooks";
import type { Balance } from "@/lib/types";

type QF = "all" | "low" | "out" | "backordered" | "incoming";

export default function WarehousePage() {
  const { can } = useAuth();
  const [tab, setTab] = useState("stock");
  const [qf, setQf] = useState<QF>("all");
  const warehouses = useLocations(["WAREHOUSE"]);
  const { data, error, reload } = useApi<Balance[]>("/inventory/balances", { location_type: "WAREHOUSE", include_zero: true });
  const { data: avail } = useApi<{ product_id: number; sku: string; product_name: string; location_code: string | null; incoming: number; awaiting_supply_demand: number }[]>("/reports/warehouse-availability");
  const inc = useMemo(() => new Map((avail ?? []).map((i) => [i.product_id, i.incoming])), [avail]);
  const demand = useMemo(() => new Map((avail ?? []).map((i) => [i.product_id, i.awaiting_supply_demand])), [avail]);
  const low = uiConfig.lowStockThreshold;
  const tests: Record<QF, (b: Balance) => boolean> = {
    all: () => true, low: (b) => b.available > 0 && b.available <= low, out: (b) => b.available === 0,
    backordered: (b) => (demand.get(b.product_id) ?? 0) > 0, incoming: (b) => (inc.get(b.product_id) ?? 0) > 0,
  };
  const count = (k: QF) => (all ?? []).filter(tests[k]).length;
  // SKUs with demand or incoming supply but no warehouse balance row yet are shown as zero stock.
  const have = new Set((data ?? []).map((b) => b.product_id));
  const missing: Balance[] = (avail ?? []).filter((a) => !have.has(a.product_id) && a.location_code === null).map((a) => ({
    location_id: 0, location_code: "—", location_name: "", location_type: "WAREHOUSE", reseller_id: null, product_id: a.product_id,
    sku: a.sku, product_name: a.product_name, on_hand: 0, reserved: 0, blocked: 0, available: 0 }));
  const all = data ? [...data, ...missing] : null;
  const rows = all?.filter(tests[qf]) ?? null;
  const total = (f: (b: Balance) => number) => (data ?? []).reduce((a, b) => a + f(b), 0);
  const short = (b: Balance) => (demand.get(b.product_id) ?? 0) > b.available;

  return (
    <>
      <PageHeader title="Warehouse" subtitle="Central warehouse stock. Available = on hand − reserved − blocked. Incoming purchase orders are not stock."
        actions={<>
          {can("inventory.receive") && <ButtonLink href="/purchasing"><PackagePlus aria-hidden />Receive goods</ButtonLink>}
          {can("replenishment.dispatch") && <ButtonLink href="/replenishment" variant="primary"><Truck aria-hidden />Pick &amp; dispatch</ButtonLink>}
        </>} />
      {data && (
        <MetricStrip items={[
          { label: "On hand", value: <NumLink href={links.movements(null, warehouses?.[0]?.id)}>{total((b) => b.on_hand).toLocaleString()}</NumLink>, hint: `${all?.length ?? data.length} SKUs` },
          { label: "Available", value: total((b) => b.available).toLocaleString(), tone: "accent" },
          { label: "Reserved", value: <NumLink href={links.reserved()}>{total((b) => b.reserved).toLocaleString()}</NumLink>, hint: "Allocated to replenishment" },
          { label: "Blocked", value: <NumLink href={links.movements(null, warehouses?.[0]?.id)}>{total((b) => b.blocked).toLocaleString()}</NumLink>, tone: total((b) => b.blocked) ? "warn" : "default", hint: "Damaged or quarantined" },
          { label: "Incoming", value: <NumLink href={links.incoming()}>{[...inc.values()].reduce((a, n) => a + n, 0).toLocaleString()}</NumLink>, tone: "info", hint: "On open purchase orders" },
        ]} />
      )}
      <Tabs active={tab} onChange={setTab} tabs={[
        { id: "stock", label: "Stock" }, { id: "ledger", label: "Movements" },
        ...(can("inventory.adjust") ? [{ id: "opening", label: "Opening balance" }] : []),
      ]} />
      <Alert>{error}</Alert>
      {tab === "stock" && (
        <>
          <div className="mb-3">
            <QuickFilters value={qf} onChange={setQf} options={[
              { id: "all", label: "All SKUs", count: all?.length }, { id: "low", label: "Low stock", count: count("low") },
              { id: "out", label: "Out of stock", count: count("out") }, { id: "backordered", label: "Backordered", count: count("backordered") },
              { id: "incoming", label: "Incoming", count: count("incoming") },
            ]} />
          </div>
          <Card padded={false}>
            <DataTable mobile="cards" rows={rows} rowKey={(b) => `${b.location_id}-${b.product_id}`} density="comfortable" label="Warehouse stock" searchPlaceholder="Search SKU or product…"
              empty={all?.length === 0 ? "No warehouse inventory yet" : "No SKUs in this view"}
              emptyHint={all?.length === 0 ? "Receive stock to begin tracking warehouse inventory." : undefined}
              emptyAction={all?.length === 0 && can("inventory.receive") ? <ButtonLink size="sm" href="/purchasing"><PackagePlus aria-hidden />Receive goods</ButtonLink> : undefined} rowClassName={(b) => short(b) && "shadow-[inset_3px_0_0_var(--color-danger)]"}
              columns={[
                { key: "p", mobile: "primary", header: "Product", mobileSort: "Tyre", value: (b) => `${b.product_name} ${b.sku}`, cell: (b) => <div className="flex items-center gap-1"><ProductCell name={b.product_name} sku={b.sku} /><StockOrigin locationId={b.location_id} productId={b.product_id} /></div> },
                { key: "loc", header: "Warehouse", value: (b) => b.location_code, cell: (b) => <span className="whitespace-nowrap text-ink-secondary">{b.location_code}</span> },
                { key: "oh", header: "On hand", align: "right", value: (b) => b.on_hand, cell: (b) => <NumLink href={links.movements(b.product_id, b.location_id)} title="Every movement of this tyre"><Qty value={b.on_hand} /></NumLink> },
                { key: "res", mobile: "field", mobileOrder: 2, header: "Reserved", align: "right", mobileSort: true, value: (b) => b.reserved, cell: (b) => <NumLink href={b.reserved ? links.reserved(b.product_id) : null} title="Who it is reserved for"><Qty value={b.reserved} /></NumLink> },
                { key: "bl", header: "Blocked", align: "right", value: (b) => b.blocked, cell: (b) => <NumLink href={b.blocked ? links.movements(b.product_id, b.location_id) : null} title="When and why it was blocked"><Qty value={b.blocked} tone="warn" /></NumLink> },
                { key: "av", mobile: "field", mobileOrder: 1, header: "Available", align: "right", mobileSort: true, value: (b) => b.available, cell: (b) => (
                  <span className="inline-flex items-center gap-2">
                    {b.available === 0 ? <Badge value="OUT" tone={(demand.get(b.product_id) ?? 0) > 0 ? "critical" : "warning"} label="Out" /> : b.available <= low ? <Badge value="LOW_STOCK" tone="warning" label="Low" /> : null}
                    <span className="text-body font-semibold"><Qty value={b.available} zeroMuted={false} /></span>
                  </span>
                ) },
                { key: "inc", header: "Incoming", align: "right", value: (b) => inc.get(b.product_id) ?? 0, cell: (b) => <NumLink href={inc.get(b.product_id) ? links.incoming(b.sku) : null} title="Open purchase orders"><Qty value={inc.get(b.product_id) ?? 0} /></NumLink> },
                { key: "dem", mobile: "field", mobileOrder: 3, header: "Demand", align: "right", value: (b) => demand.get(b.product_id) ?? 0, cell: (b) => <NumLink href={demand.get(b.product_id) ? links.demand(b.product_id) : null} title="Who is waiting for it"><Qty value={demand.get(b.product_id) ?? 0} tone={short(b) ? "danger" : undefined} /></NumLink> },
                { key: "a", mobile: "action", header: <span className="sr-only">Actions</span>, cell: (b) => b.location_id ? <StockActions row={b} onDone={reload} /> : null },
              ]} />
          </Card>
          <p className="mt-2 text-caption text-ink-secondary">Demand is open replenishment awaiting supply. Rows marked in red have more demand than available stock. “Low” means {low} or fewer units available.</p>
        </>
      )}
      {tab === "ledger" && warehouses && (
        <Card padded={false} title="Recent warehouse movements">
          <LedgerTable query={{ location_id: warehouses.find((w) => w.is_default_warehouse)?.id ?? warehouses[0]?.id }} />
        </Card>
      )}
      {tab === "opening" && <OpeningBalance onDone={() => { reload(); setTab("stock"); }} />}
    </>
  );
}

function OpeningBalance({ onDone }: { onDone: () => void }) {
  const [location, setLocation] = useState<number | "">("");
  const [lines, setLines] = useState<{ product: number | ""; qty: string }[]>([{ product: "", qty: "" }]);
  const [notes, setNotes] = useState("");
  const action = useAction();
  async function submit() {
    const ok = await action.run(() => api.post("/inventory/opening-balances", {
      location_id: location, notes: notes || null,
      lines: lines.filter((l) => l.product && Number(l.qty) > 0).map((l) => ({ product_id: l.product, quantity: Number(l.qty) })),
    }));
    if (ok) onDone();
  }
  return (
    <Card title="Post opening balance" className="max-w-3xl">
      <p className="mb-3 text-body text-ink-secondary">Use when migrating existing stock. Posts an approved ledger transaction from the opening-balance account; it never overwrites balances.</p>
      <Alert>{action.error}</Alert>
      <div className="space-y-3">
        <Field label="Location" required>{(id) => <LocationSelect id={id} types={["WAREHOUSE", "CONSIGNMENT"]} value={location} onChange={setLocation} />}</Field>
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_100px] gap-2">
            <ProductSelect value={l.product} onChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, product: v } : x)))} />
            <Input type="number" min={1} aria-label="Quantity" placeholder="Qty" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} />
          </div>
        ))}
        <Button size="sm" onClick={() => setLines((ls) => [...ls, { product: "", qty: "" }])}>Add line</Button>
        <Field label="Notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <Button variant="primary" disabled={action.busy || !location} onClick={submit}>Post opening balance</Button>
      </div>
    </Card>
  );
}
