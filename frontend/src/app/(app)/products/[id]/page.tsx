"use client";

import { ArrowLeft, Pencil } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { LedgerTable } from "@/components/Ledger";
import { ProductFormModal } from "@/components/ProductForm";
import { RequestsTable } from "@/components/tables";
import { Alert, Badge, Button, Card, DataTable, DefinitionList, Loading, MetricStrip, PageHeader, Qty, Tabs } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Balance, Product, ReplenishmentRequest } from "@/lib/types";
import { ShopLabel } from "@/components/pickers";
import { vocab } from "@/lib/terms";
import { formatAttribute, useItemSchema } from "@/lib/config";

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { data: p, error, setData } = useApi<Product>(`/products/${id}`);
  const schema = useItemSchema();
  const canInv = can("inventory.read");
  const { data: balances } = useApi<Balance[]>(canInv ? "/inventory/balances" : null, { product_id: id });
  const { data: requests } = useApi<ReplenishmentRequest[]>(can("replenishment.read") ? "/replenishment/requests" : null, { product_id: id, open_only: true });
  const [tab, setTab] = useState("stock");
  const [editing, setEditing] = useState(false);

  const split = useMemo(() => {
    const rows = balances ?? [];
    const wh = rows.filter((b) => b.location_type === "WAREHOUSE");
    const cons = rows.filter((b) => b.location_type === "CONSIGNMENT");
    const sum = (r: Balance[], f: (b: Balance) => number) => r.reduce((a, b) => a + f(b), 0);
    return { wh, cons, whAvail: sum(wh, (b) => b.available), whOnHand: sum(wh, (b) => b.on_hand), consOnHand: sum(cons, (b) => b.on_hand),
      consAvail: sum(cons, (b) => b.available), transit: sum(rows.filter((b) => b.location_type === "TRANSIT"), (b) => b.on_hand) };
  }, [balances]);
  const awaiting = (requests ?? []).reduce((a, r) => a + r.qty_awaiting_supply, 0);

  if (error) return <Alert>{error}</Alert>;
  if (!p) return <Loading />;

  return (
    <>
      <Link href="/products" className="mb-3 inline-flex items-center gap-1.5 text-label text-ink-secondary hover:text-ink"><ArrowLeft className="size-3.5" aria-hidden />Products</Link>
      <PageHeader eyebrow={p.brand}
        title={<span className="flex flex-wrap items-center gap-3">{p.pattern} <span className="rounded-md bg-neutral-soft px-2 py-0.5 data text-heading font-semibold">{p.size_display}</span> <Badge value={p.is_active ? "ACTIVE" : "CLOSED"} label={p.is_active ? "Active" : "Inactive"} /></span>}
        meta={<><span>SKU <span className="sku text-ink">{p.sku}</span></span>{schema.tyreFields && p.load_index && <span>Load / speed <span className="text-ink">{p.load_index}{p.speed_rating}</span></span>}
          {p.barcode && <span>Barcode <span className="sku text-ink">{p.barcode}</span></span>}</>}
        actions={can("catalogue.write") && <Button onClick={() => setEditing(true)}><Pencil aria-hidden />Edit product</Button>} />

      {balances && (
        <MetricStrip items={[
          { label: "Warehouse available", value: split.whAvail, tone: split.whAvail === 0 ? "danger" : "accent", hint: `${split.whOnHand} on hand` },
          { label: "Consignment stock", value: split.consOnHand, hint: `${split.consAvail} available at ${split.cons.filter((b) => b.on_hand > 0).length} locations` },
          { label: "In transit", value: split.transit, tone: "info" },
          { label: "Awaiting supply", value: awaiting, tone: awaiting ? "warn" : "default", hint: `${(requests ?? []).length} open request(s)` },
        ]} />
      )}

      <Tabs active={tab} onChange={setTab} tabs={[
        { id: "stock", label: "Stock by location" }, { id: "demand", label: "Outstanding demand", count: requests?.length },
        { id: "moves", label: "Recent movement" }, { id: "details", label: "Details" },
      ]} />

      {tab === "stock" && (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-3">
          <Card title="Warehouse" padded={false}>
            <DataTable search={false} rows={split.wh} rowKey={(b) => b.location_id} empty="Not stocked in the warehouse"
              columns={[
                { key: "l", header: "Warehouse", cell: (b) => <ShopLabel code={b.location_code} /> },
                { key: "oh", header: "On hand", align: "right", cell: (b) => <Qty value={b.on_hand} /> },
                { key: "av", header: "Available", align: "right", cell: (b) => <span className="font-semibold"><Qty value={b.available} zeroMuted={false} /></span> },
              ]} />
          </Card>
          <Card title={`${vocab.Partner} consignment stock`} className="xl:col-span-2" padded={false}>
            <DataTable label="Stock by location" rows={split.cons.filter((b) => b.on_hand > 0)} rowKey={(b) => b.location_id} pageSize={20} searchPlaceholder="Search location…"
              empty={`No ${vocab.partner} holds this product`}
              columns={[
                { key: "l", header: "Location", value: (b) => `${b.location_code} ${b.location_name}`, cell: (b) => (
                  <div>{b.reseller_id ? <Link className="link" href={`/resellers/${b.reseller_id}`}>{b.location_name}</Link> : b.location_name}<div className="text-caption text-ink-muted">{b.location_code}</div></div>
                ) },
                { key: "oh", header: "On hand", align: "right", value: (b) => b.on_hand, cell: (b) => <Qty value={b.on_hand} /> },
                { key: "rs", header: "Reserved", align: "right", cell: (b) => <Qty value={b.reserved} /> },
                { key: "bl", header: "Blocked", align: "right", cell: (b) => <Qty value={b.blocked} tone="warn" /> },
                { key: "av", header: "Available", align: "right", value: (b) => b.available, cell: (b) => <span className="font-semibold"><Qty value={b.available} /></span> },
              ]} />
          </Card>
        </div>
      )}
      {tab === "demand" && <Card padded={false}><RequestsTable rows={requests} showReseller empty="No open demand for this product" /></Card>}
      {tab === "moves" && <Card padded={false} title="Ledger movements"><LedgerTable query={{ product_id: p.id }} /></Card>}
      {tab === "details" && (
        <Card title="Product details">
          <DefinitionList items={[
            ["SKU", <span key="s" className="sku">{p.sku}</span>], [schema.brandLabel, p.brand], [schema.nameLabel, p.pattern],
            [schema.specLabel, p.size_display || "—"],
            ...(p.width !== null
              ? [["Width / aspect / rim", `${p.width} / ${p.aspect_ratio} / ${p.rim_diameter}″`], ["Load index", p.load_index], ["Speed rating", p.speed_rating]] as [string, string | null][]
              : schema.attributes.map((a) => [a.unit ? `${a.label} (${a.unit})` : a.label, formatAttribute(a, p.attributes?.[a.key])] as [string, string])),
            ["Barcode", p.barcode],
            ["Description", p.description],
          ]} />
        </Card>
      )}
      {editing && <ProductFormModal product={p} onClose={() => setEditing(false)} onSaved={(saved) => { setEditing(false); setData(saved); }} />}
    </>
  );
}
