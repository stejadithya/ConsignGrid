"use client";

import { Download, FileSpreadsheet, Pencil, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ProductFormModal } from "@/components/ProductForm";
import { EXPORT_URL, ProductImportModal, TEMPLATE_URL } from "@/components/ProductImport";
import {
  Alert, Badge, Button, buttonClass, Card, type Column, cx, DataTable, FilterField, Input, MoreMenu, PageHeader, Qty,
  Select,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Product } from "@/lib/types";
import { branding } from "@/config/branding";
import { vocab } from "@/lib/terms";
import { useItemSchema } from "@/lib/config";

interface Demand { product_id: number; awaiting_supply: number; warehouse_available: number }
interface ConsignmentReport { rows: { product_id: number; on_hand: number }[] }

export default function ProductsPage() {
  const { can } = useAuth();
  const router = useRouter();
  const [active, setActive] = useState("true");
  const [brand, setBrand] = useState("");
  const [size, setSize] = useState("");
  const schema = useItemSchema();
  const [stock, setStock] = useState("");
  const { data, error, reload } = useApi<Product[]>("/products", { active: active === "" ? undefined : active, limit: 1000 });
  const canStock = can("report.read") && can("inventory.read");
  const { data: demand } = useApi<Demand[]>(canStock ? "/reports/demand-by-sku" : null);
  const { data: wh } = useApi<{ product_id: number; available: number }[]>(canStock ? "/reports/warehouse-availability" : null);
  const { data: cons } = useApi<ConsignmentReport>(canStock ? "/reports/consignment-stock" : null);
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [importing, setImporting] = useState(false);

  const whMap = useMemo(() => new Map((wh ?? []).map((w) => [w.product_id, w.available])), [wh]);
  const backMap = useMemo(() => new Map((demand ?? []).map((d) => [d.product_id, d.awaiting_supply])), [demand]);
  const consMap = useMemo(() => {
    const m = new Map<number, number>();
    (cons?.rows ?? []).forEach((r) => m.set(r.product_id, (m.get(r.product_id) ?? 0) + r.on_hand));
    return m;
  }, [cons]);
  const brands = useMemo(() => [...new Set((data ?? []).map((p) => p.brand))].sort(), [data]);

  const rows = useMemo(() => data?.filter((p) => {
    if (brand && p.brand !== brand) return false;
    if (size.trim() && !p.size_display.toLowerCase().replace(/\s/g, "").includes(size.toLowerCase().replace(/\s/g, ""))) return false;
    const w = whMap.get(p.id) ?? 0, b = backMap.get(p.id) ?? 0;
    if (stock === "in" && w <= 0) return false;
    if (stock === "out" && w > 0) return false;
    if (stock === "back" && b <= 0) return false;
    return true;
  }) ?? null, [data, brand, size, stock, whMap, backMap]);

  const stockCols: Column<Product>[] = canStock ? [
    { key: "wh", header: "Warehouse", align: "right", mobile: "field", mobileSort: "Warehouse stock", value: (p) => whMap.get(p.id) ?? 0, cell: (p) => <Qty value={whMap.get(p.id) ?? 0} zeroMuted={false} tone={(whMap.get(p.id) ?? 0) === 0 ? "danger" : undefined} /> },
    { key: "cons", header: "Consignment", align: "right", mobile: "field", mobileLabel: `At ${vocab.partners}`, value: (p) => consMap.get(p.id) ?? 0, cell: (p) => <Qty value={consMap.get(p.id) ?? 0} /> },
    { key: "back", header: "Backorder", align: "right", mobile: "field", mobileSort: true, value: (p) => backMap.get(p.id) ?? 0, cell: (p) => <Qty value={backMap.get(p.id) ?? 0} tone="warn" /> },
  ] : [];

  return (
    <>
      <PageHeader mobileActions={<>
          <MoreMenu items={[
            can("catalogue.import") && { label: "Excel template", href: TEMPLATE_URL, download: true, icon: Download },
            can("catalogue.import") && { label: "Export all SKUs (Excel)", href: EXPORT_URL, download: true, icon: FileSpreadsheet },
            can("catalogue.import") && { label: "Import from Excel", icon: Upload, onSelect: () => setImporting(true) },
          ]} />
          {can("catalogue.create") && <Button variant="primary" onClick={() => setEditing("new")}><Plus aria-hidden />Add product</Button>}
        </>}
        title="Products" subtitle={`Product catalogue: what ${branding.companyName} supplies. A product in the catalogue does not mean stock exists — stock appears only once it is received.`}
        actions={<>
          {can("catalogue.import") && (
            <a href={TEMPLATE_URL} download className={cx(buttonClass(), "max-sm:hidden")}>
              <Download className="size-4" aria-hidden />Excel template
            </a>
          )}
          {can("catalogue.import") && (
            <a href={EXPORT_URL} download title="Edit or add rows, then use Import from Excel."
              className={buttonClass()}>
              <FileSpreadsheet className="size-4" aria-hidden />Export all SKUs (Excel)
            </a>
          )}
          {can("catalogue.import") && <Button onClick={() => setImporting(true)}><Upload aria-hidden />Import from Excel</Button>}
          {can("catalogue.create") && <Button variant="primary" onClick={() => setEditing("new")}><Plus aria-hidden />Add product</Button>}
        </>} />
      <Alert>{error}</Alert>
      {/* The dealer price-list image is hidden: prices are managed in Xero (D2). */}
      {can("catalogue.import") && <p className="mb-3 text-caption text-ink-secondary">Export all SKUs (Excel): edit or add rows, then use Import from Excel.</p>}
      <Card padded={false}>
        <DataTable rows={rows} rowKey={(p) => p.id} searchPlaceholder={`Search SKU, ${schema.brandLabel.toLowerCase()}, ${schema.nameLabel.toLowerCase()}…`} mobile="cards" label="Products"
          onRowClick={(p) => router.push(`/products/${p.id}`)}
          empty={data?.length === 0 && active === "true" && !brand && !size && !stock ? "No products in the catalogue yet" : "No products match"}
          emptyHint={data?.length === 0 && active === "true" ? "Import the product master from Excel using the standard template, or add products one at a time." : "Adjust the filters, or add a product to the catalogue."}
          emptyAction={can("catalogue.import") && data?.length === 0 ? <Button size="sm" variant="primary" onClick={() => setImporting(true)}><Upload aria-hidden />Import from Excel</Button> : undefined}
          filterCount={[brand, size, stock, active !== "true"].filter(Boolean).length}
          onClearFilters={() => { setBrand(""); setSize(""); setStock(""); setActive("true"); }}
          filters={<>
            <FilterField label="Brand" className="w-40"><Select aria-label="Brand filter" value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="All brands" options={brands.map((b) => ({ value: b, label: b }))} /></FilterField>
            <FilterField label={schema.specLabel} className="w-36"><Input aria-label={`${schema.specLabel} filter`} placeholder={schema.tyreFields ? "Size e.g. 205/55" : schema.specLabel} value={size} onChange={(e) => setSize(e.target.value)} /></FilterField>
            {canStock && <FilterField label="Availability" className="w-44"><Select aria-label="Stock filter" value={stock} onChange={(e) => setStock(e.target.value)} placeholder="Any availability"
              options={[{ value: "in", label: "In stock (warehouse)" }, { value: "out", label: "Out of stock" }, { value: "back", label: "Has backorders" }]} /></FilterField>}
            <FilterField label="Status" className="w-36"><Select aria-label="Status filter" value={active} onChange={(e) => setActive(e.target.value)}
              options={[{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }]} placeholder="All statuses" /></FilterField>
          </>}
          columns={[
            { key: "id", header: "Product", mobileSort: "Name", value: (p) => `${p.brand} ${p.pattern} ${p.sku}`, cell: (p) => (
              <div className="min-w-0">
                <Link href={`/products/${p.id}`} className="font-medium text-ink hover:underline hover:decoration-brand hover:decoration-2 hover:underline-offset-4" onClick={(e) => e.stopPropagation()}>{p.brand} {p.pattern}</Link>
                <div className="sku text-label text-ink-secondary">{p.sku}</div>
              </div>
            ) },
            { key: "size", header: schema.specLabel, mobile: "secondary", mobileSort: true, value: (p) => p.size_display, cell: (p) => (
              <div><span className="font-semibold text-ink">{p.size_display}</span>{(p.load_index || p.speed_rating) && <span className="ml-1.5 text-caption text-ink-muted">{p.load_index}{p.speed_rating}</span>}</div>
            ) },
            { key: "st", header: "Status", mobile: "status", cell: (p) => <Badge value={p.is_active ? "ACTIVE" : "CLOSED"} label={p.is_active ? "Active" : "Inactive"} /> },
            ...stockCols,
            ...(can("catalogue.write") ? [{ key: "e", header: <span className="sr-only">Actions</span>, mobile: "action" as const, cell: (p: Product) => (
              <Button size="sm" variant="ghost" aria-label={`Edit ${p.sku}`} onClick={(e) => { e.stopPropagation(); setEditing(p); }}><Pencil aria-hidden />Edit</Button>
            ) }] : []),
          ]} />
      </Card>
      {importing && <ProductImportModal onClose={() => setImporting(false)} onImported={reload} />}
      {editing && <ProductFormModal product={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}
