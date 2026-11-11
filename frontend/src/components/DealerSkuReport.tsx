"use client";

/** Report by dealer, by SKU (finding 31): per shop and tyre, stock, on the way, waiting, and sold/invoiced in the
 * period, grouped by dealer with totals. Units only. Dealers see only their own (the API scopes it). */

import { Download } from "lucide-react";
import { useState } from "react";
import { withQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, todayIso } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ResellerSelect } from "./pickers";
import { Alert, buttonClass, Card, DataTable, Empty, Field, Input, Loading, ProductCell, Qty } from "./ui";

const METRICS = [
  ["on_hand", "On hand"], ["available", "Available"], ["held", "Held"], ["on_the_way", "On the way"],
  ["waiting", "Waiting"], ["sold", "Sold"], ["invoiced", "Invoiced"], ["not_invoiced", "Not yet invoiced"],
] as const;
type Metric = (typeof METRICS)[number][0];
type Numbers = Record<Metric, number>;
interface Row extends Numbers { location_id: number; location_code: string; shop: string; city: string | null; product_id: number; sku: string; tyre: string }
interface Group { reseller_id: number; reseller_name: string; account_ref: string; rows: Row[]; totals: Numbers }
interface Report { date_from: string; date_to: string; dealers: Group[]; totals: Numbers }

const monthStart = () => `${todayIso().slice(0, 8)}01`;

export function DealerSkuReport() {
  const { user } = useAuth();
  const staff = !user?.reseller_id;
  const [reseller, setReseller] = useState<number | "">("");
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(todayIso());
  const query = { reseller_id: reseller, date_from: from, date_to: to };
  const { data, error } = useApi<Report>("/reports/dealer-sku", query);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        {staff && <div className="w-72"><Field label="Dealer">{(id) => <ResellerSelect id={id} value={reseller} onChange={setReseller} />}</Field></div>}
        <div className="w-44"><Field label="Sold from">{(id) => <Input id={id} type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />}</Field></div>
        <div className="w-44"><Field label="to">{(id) => <Input id={id} type="date" value={to} min={from} max={todayIso()} onChange={(e) => setTo(e.target.value)} />}</Field></div>
        <a href={withQuery("/api/reports/dealer-sku.xlsx", query)} download
          className={buttonClass()}>
          <Download className="size-4" aria-hidden />Download Excel
        </a>
      </div>
      <Alert>{error}</Alert>
      {!data && !error && <Loading />}
      {data && (
        <p className="mb-3 text-label text-ink-secondary">
          Stock is as of now; sold and invoiced count sales dated {fmtDate(data.date_from)} – {fmtDate(data.date_to)}. Held = reserved + blocked.
          Waiting = replacements and requests still awaiting supply. Units only.
        </p>
      )}
      {data && !data.dealers.length && <Card><Empty>Nothing to show for this period.</Empty></Card>}
      <div className="space-y-4">
        {data?.dealers.map((g) => (
          <Card key={g.reseller_id} padded={false} title={<>{g.reseller_name} <span className="sku text-label text-ink-secondary">{g.account_ref}</span></>}
            subtitle={METRICS.map(([k, label]) => `${label} ${g.totals[k]}`).join(" · ")}>
            <DataTable label="Stock and sales by SKU" search={g.rows.length > 10} pageSize={50} rows={[...g.rows, { ...g.totals, location_id: 0, location_code: "", shop: "Total", city: null, product_id: 0, sku: "", tyre: "" }]}
              rowKey={(r) => `${r.location_id}-${r.product_id}`}
              rowClassName={(r) => r.location_id === 0 && "bg-subtle font-semibold"}
              columns={[
                { key: "s", header: "Shop", value: (r) => `${r.shop} ${r.city ?? ""}`, cell: (r) => r.location_id === 0 ? <b>Total</b>
                  : <div>{r.shop}<div className="text-caption text-ink-muted">{[r.city, r.location_code].filter(Boolean).join(" · ")}</div></div> },
                { key: "t", header: "Tyre", value: (r) => `${r.sku} ${r.tyre}`, className: "min-w-56 whitespace-normal",
                  cell: (r) => r.location_id === 0 ? "" : <ProductCell name={r.tyre} sku={r.sku} /> },
                ...METRICS.map(([k, label]) => ({ key: k, header: label, align: "right" as const, value: (r: Row) => r[k],
                  cell: (r: Row) => <Qty value={r[k]} tone={k === "not_invoiced" && r[k] ? "warn" : k === "waiting" && r[k] ? "warn" : undefined} /> })),
              ]} />
          </Card>
        ))}
      </div>
    </>
  );
}
