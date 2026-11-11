"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { FilteredTo, links, NumLink } from "./NumLink";
import { LedgerTable } from "./Ledger";
import { LocationSelect, ProductSelect, useTyreName } from "./pickers";
import { Alert, Badge, Card, DataTable, MetricStrip, PageHeader, ProductCell, Qty, QuickFilters } from "./ui";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { InventoryOverviewRow, StockAllocationRow } from "@/lib/types";

/** Stock overview: Total = warehouse on hand + shipped (in transit); Available = Total − Reserved − Shipped (− Blocked). */
export function StockOverview() {
  const { data, error } = useApi<InventoryOverviewRow[]>("/stock-requests/inventory/overview");
  const [qf, setQf] = useState<"all" | "low" | "pending">("all");
  const rows = useMemo(() => data?.filter((r) => qf === "all" || (qf === "low" ? r.available <= 0 : r.requested_pending > 0)) ?? null, [data, qf]);
  const sum = (k: keyof InventoryOverviewRow) => (data ?? []).reduce((a, r) => a + Number(r[k]), 0);
  return (
    <>
      <PageHeader eyebrow="Inventory" title="Stock overview"
        subtitle="Available = Total − Reserved − Shipped. Total is warehouse stock plus stock shipped and still in transit; delivered stock sits with dealers on consignment." />
      <Alert>{error}</Alert>
      <MetricStrip items={[
        { label: "Total", value: <NumLink href={links.movements()}>{sum("total").toLocaleString()}</NumLink>, hint: "Warehouse + in transit" },
        { label: "Available", value: sum("available").toLocaleString(), tone: "accent", hint: "Free to approve" },
        { label: "Reserved", value: <NumLink href={links.reserved()}>{sum("reserved").toLocaleString()}</NumLink>, tone: "info", hint: "Approved, not shipped" },
        { label: "Shipped", value: <NumLink href={links.deliveries()}>{sum("shipped").toLocaleString()}</NumLink>, hint: "In transit" },
        { label: "Delivered", value: <NumLink href={links.atDealers()}>{sum("delivered").toLocaleString()}</NumLink>, tone: "ok", hint: "At dealers (consignment)" },
      ]} />
      <Card padded={false}>
        <DataTable label="Stock by tyre" rows={rows} rowKey={(r) => r.product_id} searchPlaceholder="Search SKU or tyre…"
          empty="No stock recorded yet" emptyHint="Stock appears once goods are received or opening balances are posted."
          quickFilters={<QuickFilters value={qf} onChange={setQf} options={[
            { id: "all", label: "All SKUs", count: data?.length },
            { id: "low", label: "Nothing available", count: data?.filter((r) => r.available <= 0).length },
            { id: "pending", label: "Awaiting approval", count: data?.filter((r) => r.requested_pending > 0).length },
          ]} />}
          columns={[
            { key: "p", pin: true, header: "SKU", value: (r) => `${r.sku} ${r.product_name}`, cell: (r) => (
              <div className="flex items-center gap-2"><Link href={`/products/${r.product_id}`} onClick={(e) => e.stopPropagation()}><ProductCell sku={r.sku} name={r.product_name} /></Link>
                {!r.is_active && <Badge value="CLOSED" label="Inactive" />}</div>
            ) },
            { key: "t", header: "Total", align: "right", value: (r) => r.total, cell: (r) => <NumLink href={links.movements(r.product_id)} title="Every movement of this tyre"><span className="num font-semibold">{r.total}</span></NumLink> },
            { key: "a", header: "Available", align: "right", value: (r) => r.available, cell: (r) => <NumLink href={links.whereIs(r.product_id)} title="Where it is: warehouse and dealers"><Qty value={r.available} zeroMuted={false} tone={r.available <= 0 ? "danger" : "ok"} /></NumLink> },
            { key: "r", header: "Reserved", align: "right", value: (r) => r.reserved, cell: (r) => <NumLink href={r.reserved ? links.reserved(r.product_id) : null} title="Who it is reserved for"><Qty value={r.reserved} /></NumLink> },
            { key: "s", header: "Shipped", align: "right", value: (r) => r.shipped, cell: (r) => <NumLink href={r.shipped ? links.movements(r.product_id) : null} title="Shipments on the way"><Qty value={r.shipped} /></NumLink> },
            { key: "b", header: "Blocked", align: "right", value: (r) => r.blocked, cell: (r) => <NumLink href={r.blocked ? links.movements(r.product_id) : null} title="When and why it was blocked"><Qty value={r.blocked} tone="warn" /></NumLink> },
            { key: "d", header: "Delivered", align: "right", value: (r) => r.delivered, cell: (r) => <NumLink href={r.delivered ? links.atDealers(r.sku) : null} title="Which dealers hold it"><Qty value={r.delivered} /></NumLink> },
            { key: "q", header: "Requested (pending)", align: "right", value: (r) => r.requested_pending, cell: (r) => <NumLink href={r.requested_pending ? links.pendingRequests() : null} title="Requests waiting for approval"><Qty value={r.requested_pending} tone="warn" /></NumLink> },
          ]} />
      </Card>
    </>
  );
}

/** Stock allocation: warehouse stock reserved for resellers (approved, not yet shipped). */
export function StockAllocation() {
  const params = useSearchParams();
  const product = params.get("product_id") ? Number(params.get("product_id")) : undefined;
  const tyreName = useTyreName();
  const { data, error } = useApi<StockAllocationRow[]>("/stock-requests/inventory/allocations", { product_id: product });
  const total = (data ?? []).reduce((a, r) => a + r.open_qty, 0);
  return (
    <>
      <PageHeader eyebrow="Inventory" title="Stock allocation"
        subtitle="Warehouse stock reserved for dealers. Reserved stock cannot be approved for anyone else until it ships or is released." />
      <Alert>{error}</Alert>
      {product && <FilteredTo label={`Reservations of ${tyreName({ productId: product }) ?? "this tyre"}`} clearHref="/inventory/allocation" />}
      <MetricStrip items={[
        { label: "Reserved units", value: total.toLocaleString(), tone: "info" },
        { label: "Reservations", value: (data ?? []).length },
        { label: "SKUs", value: new Set((data ?? []).map((r) => r.product_id)).size },
      ]} />
      <Card padded={false}>
        <DataTable rows={data} rowKey={(r) => r.allocation_id} searchPlaceholder="Search SKU, dealer, request…" label="Reservations"
          empty="Nothing reserved" emptyHint="Approved stock requests and allocated replenishment reserve warehouse stock here."
          columns={[
            { key: "p", header: "SKU", value: (r) => `${r.sku} ${r.product_name}`, cell: (r) => <ProductCell sku={r.sku} name={r.product_name} /> },
            { key: "r", header: "Dealer", value: (r) => r.reseller_name, cell: (r) => <div><div>{r.reseller_name}</div><div className="text-caption text-ink-muted">{r.location_code}</div></div> },
            { key: "q", header: "Reserved", align: "right", value: (r) => r.open_qty, cell: (r) => <span className="num font-semibold">{r.open_qty}</span> },
            { key: "sr", header: "Stock request", value: (r) => r.stock_request_number, cell: (r) => r.stock_request_id
              ? <Link className="link" href={`/stock-requests/${r.stock_request_id}`}>{r.stock_request_number}</Link> : <span className="text-ink-muted">—</span> },
            { key: "rp", header: "Replenishment", value: (r) => r.replenishment_number, cell: (r) => <Link className="link" href={`/replenishment/${r.replenishment_request_id}`}>{r.replenishment_number}</Link> },
            { key: "d", header: "Reserved on", value: (r) => r.created_at, cell: (r) => <span className="text-ink-secondary">{fmtDateTime(r.created_at)}</span> },
          ]} />
      </Card>
    </>
  );
}

/** Stock movement: the inventory ledger, filterable by location and SKU. */
export function StockMovement() {
  // Opened from a clicked number: start filtered to that tyre / location.
  const params = useSearchParams();
  const [location, setLocation] = useState<number | "">(params.get("location_id") ? Number(params.get("location_id")) : "");
  const [product, setProduct] = useState<number | "">(params.get("product_id") ? Number(params.get("product_id")) : "");
  const number = params.get("number") ?? undefined;   // one movement, opened from the search box
  return (
    <>
      <PageHeader eyebrow="Inventory" title="Stock movement"
        subtitle="Every stock movement from the ledger: receipts, reservations, shipments, deliveries, sales, transfers and adjustments." />
      <Card className="mb-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <LocationSelect value={location} onChange={setLocation} types={["WAREHOUSE", "CONSIGNMENT", "TRANSIT"]} placeholder="All locations" />
          <ProductSelect value={product} onChange={setProduct} />
        </div>
      </Card>
      <Card padded={false}>
        <LedgerTable query={{ location_id: location || undefined, product_id: product || undefined, number }} />
      </Card>
    </>
  );
}
