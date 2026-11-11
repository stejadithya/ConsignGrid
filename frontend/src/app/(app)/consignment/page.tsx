"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { ResellerSelect } from "@/components/pickers";
import { links, NumLink } from "@/components/NumLink";
import { StockOrigin } from "@/components/StockOrigin";
import {
  Alert, Card, DataTable, FilterField, Input, MetricStrip, PageHeader, ProductCell, Qty, Select,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { vocab } from "@/lib/terms";
import { branding } from "@/config/branding";

interface Row {
  reseller_id: number; reseller_name: string; account_ref: string; location_id: number; location_code: string;
  product_id: number; sku: string; brand: string; size: string; product_name: string; on_hand: number; reserved: number;
  blocked: number; available: number; value: string | null;
}
interface Report {
  rows: Row[]; in_transit_total: number; note: string;
  totals: { on_hand: number; reserved: number; blocked: number; available: number; value: string | null; locations: number; resellers: number };
}

/** Mandatory report 11.1 — total unsold dealership-owned stock at reseller locations. */
export default function ConsignmentStockPage() {
  const { user } = useAuth();
  const [reseller, setReseller] = useState<number | "">("");
  const [brand, setBrand] = useState("");
  const params = useSearchParams();   // opened from "Delivered" on Stock Overview
  const [sku, setSku] = useState(params.get("sku") ?? "");
  const [size, setSize] = useState("");
  const [availability, setAvailability] = useState("");
  const [w, a, r] = size.split(/[/R\s]+/i).map((x) => x.trim());
  const { data, error } = useApi<Report>("/reports/consignment-stock", {
    reseller_id: reseller, brand, sku, availability,
    width: w && /^\d+$/.test(w) ? w : undefined, aspect_ratio: a && /^\d+$/.test(a) ? a : undefined,
    rim_diameter: r && /^[\d.]+$/.test(r) ? r : undefined,
  });
  return (
    <>
      <PageHeader title="Consignment stock" subtitle={data?.note ?? `Unsold ${branding.companyName}-owned stock at ${vocab.partner} locations`} />
      <Alert>{error}</Alert>
      {data && (
        <MetricStrip items={[
          { label: `On hand at ${vocab.partners}`, value: data.totals.on_hand.toLocaleString(), tone: "accent", hint: `${data.totals.locations} locations · ${data.totals.resellers} ${vocab.partners}` },
          { label: "Available", value: data.totals.available.toLocaleString(), hint: "For sale or transfer" },
          { label: "Reserved / blocked", value: `${data.totals.reserved} / ${data.totals.blocked}` },
          { label: "In transit", value: <NumLink href={links.deliveries()}>{data.in_transit_total.toLocaleString()}</NumLink>, tone: "info", hint: "Counted separately, never in a location" },
        ]} />
      )}
      <Card padded={false}>
        <DataTable mobile="cards" label="Consignment stock" rows={data?.rows} rowKey={(x) => `${x.location_id}-${x.product_id}`} search={false} pageSize={100}
          empty={brand || sku || size || availability || reseller ? "No consignment stock matches these filters" : "No stock has been placed on consignment yet"}
          emptyHint={brand || sku || size || availability || reseller ? undefined : `Consignment stock appears once stock is delivered or opening balances are posted at ${vocab.partner} locations.`}
          filterCount={[reseller, brand, sku, size, availability].filter(Boolean).length}
          onClearFilters={() => { setReseller(""); setBrand(""); setSku(""); setSize(""); setAvailability(""); }}
          filters={<>
            {!user?.reseller_id && <FilterField label={vocab.Partner} className="w-56"><ResellerSelect value={reseller} onChange={setReseller} /></FilterField>}
            <FilterField label="Brand" className="w-32"><Input aria-label="Brand" placeholder="Brand" value={brand} onChange={(e) => setBrand(e.target.value)} /></FilterField>
            <FilterField label="SKU" className="w-36"><Input aria-label="SKU" placeholder="SKU contains" value={sku} onChange={(e) => setSku(e.target.value)} /></FilterField>
            <FilterField label="Size" className="w-36"><Input aria-label="Size" placeholder="Size e.g. 205/55R16" value={size} onChange={(e) => setSize(e.target.value)} /></FilterField>
            <FilterField label="Availability" className="w-40"><Select aria-label="Availability" value={availability} onChange={(e) => setAvailability(e.target.value)} placeholder="Any stock status"
              options={[{ value: "available", label: "Has available" }, { value: "reserved", label: "Has reserved" }, { value: "blocked", label: "Has blocked" }]} /></FilterField>
          </>}
          columns={[
            { key: "r", mobile: "secondary", header: vocab.Partner, mobileSort: true, value: (x) => x.reseller_name, cell: (x) => <div className="min-w-0"><div className="truncate">{x.reseller_name}</div><div className="text-caption text-ink-muted">{x.location_code}</div></div> },
            { key: "s", mobile: "primary", header: "Product", mobileSort: `${vocab.Item} (SKU)`, value: (x) => `${x.sku} ${x.product_name}`, cell: (x) => <div className="flex items-center gap-1"><ProductCell name={x.product_name} sku={x.sku} /><StockOrigin locationId={x.location_id} productId={x.product_id} /></div> },
            { key: "z", header: "Size", value: (x) => x.size, cell: (x) => <span className="font-medium">{x.size}</span> },
            { key: "oh", mobile: "field", mobileOrder: 2, header: "On hand", align: "right", value: (x) => x.on_hand, cell: (x) => <NumLink href={links.movements(x.product_id, x.location_id)} title={`Every movement at this ${vocab.partner}`}><Qty value={x.on_hand} /></NumLink> },
            { key: "av", mobile: "field", mobileOrder: 1, header: "Available", align: "right", mobileSort: true, value: (x) => x.available, cell: (x) => <span className="font-semibold"><Qty value={x.available} /></span> },
            { key: "rs", header: "Reserved", align: "right", value: (x) => x.reserved, cell: (x) => <NumLink href={x.reserved ? links.movements(x.product_id, x.location_id) : null} title="What it is reserved for"><Qty value={x.reserved} /></NumLink> },
            { key: "bl", header: "Blocked", align: "right", value: (x) => x.blocked, cell: (x) => <NumLink href={x.blocked ? links.movements(x.product_id, x.location_id) : null} title="When and why it was blocked"><Qty value={x.blocked} tone="warn" /></NumLink> },
          ]} />
      </Card>
    </>
  );
}
