"use client";

import { ShoppingCart } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Alert, Badge, ButtonLink, Card, DataTable, Field, Input, MetricStrip, PageHeader, ProductCell, QuickFilters } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDate, todayIso } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Sale } from "@/lib/types";

type Preset = "today" | "week" | "month" | "last_month" | "year" | "custom";
type Group = "day" | "week" | "month";

const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const parse = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
/** Monday of the week containing the date. */
const weekStart = (s: string) => { const d = parse(s); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };

function range(preset: Preset, from: string, to: string): [string, string] {
  const today = todayIso();
  const t = parse(today);
  switch (preset) {
    case "today": return [today, today];
    case "week": return [weekStart(today), today];
    case "month": return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), today];
    case "last_month": return [iso(new Date(t.getFullYear(), t.getMonth() - 1, 1)), iso(new Date(t.getFullYear(), t.getMonth(), 0))];
    case "year": return [iso(new Date(t.getFullYear(), 0, 1)), today];
    default: return [from || today, to || today];
  }
}

function bucket(date: string, group: Group): { key: string; label: string } {
  if (group === "day") return { key: date, label: fmtDate(date) };
  if (group === "week") { const w = weekStart(date); return { key: w, label: `Week of ${fmtDate(w)}` }; }
  const d = parse(date);
  return { key: date.slice(0, 7), label: d.toLocaleDateString(undefined, { month: "long", year: "numeric" }) };
}

/** A reseller's own sales for a chosen period: totals, by tyre, by day / week / month, and every sale. */
export default function MySalesPage() {
  const { can } = useAuth();
  const [preset, setPreset] = useState<Preset>("month");
  const [from, setFrom] = useState(todayIso());
  const [to, setTo] = useState(todayIso());
  const [group, setGroup] = useState<Group>("day");
  const [dateFrom, dateTo] = range(preset, from, to);
  const { data, error } = useApi<Sale[]>("/sales", { date_from: dateFrom, date_to: dateTo, limit: 5000 });

  const sales = useMemo(() => data ?? [], [data]);
  const units = sales.reduce((a, s) => a + s.lines.reduce((b, l) => b + l.chargeable_qty, 0), 0);

  const byTyre = useMemo(() => {
    const m = new Map<number, { product_id: number; sku: string | null; name: string | null; units: number }>();
    for (const s of sales) for (const l of s.lines) {
      const r = m.get(l.product_id) ?? { product_id: l.product_id, sku: l.sku, name: l.product_name, units: 0 };
      r.units += l.chargeable_qty;
      m.set(l.product_id, r);
    }
    return [...m.values()].filter((r) => r.units > 0).sort((a, b) => b.units - a.units);
  }, [sales]);

  const byPeriod = useMemo(() => {
    const m = new Map<string, { key: string; label: string; sales: number; units: number }>();
    for (const s of sales) {
      const b = bucket(s.sale_date, group);
      const r = m.get(b.key) ?? { ...b, sales: 0, units: 0 };
      r.sales += 1;
      r.units += s.lines.reduce((a, l) => a + l.chargeable_qty, 0);
      m.set(b.key, r);
    }
    return [...m.values()].sort((a, b) => b.key.localeCompare(a.key));
  }, [sales, group]);

  return (
    <>
      <PageHeader title="My sales" subtitle="Tyres you have sold in the period you choose. Pick a quick period or select dates on the calendar."
        actions={can("sales.record") && <ButtonLink href="/sales" variant="primary"><ShoppingCart aria-hidden />Report a sale</ButtonLink>} />
      <Alert>{error}</Alert>
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-4">
          <QuickFilters label="Period" value={preset} onChange={setPreset} options={[
            { id: "today", label: "Today" }, { id: "week", label: "This week" }, { id: "month", label: "This month" },
            { id: "last_month", label: "Last month" }, { id: "year", label: "This year" }, { id: "custom", label: "Choose dates" },
          ]} />
          {preset === "custom" && (
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-44"><Field label="From">{(id) => <Input id={id} type="date" max={to} value={from} onChange={(e) => setFrom(e.target.value)} />}</Field></div>
              <div className="w-44"><Field label="To">{(id) => <Input id={id} type="date" min={from} max={todayIso()} value={to} onChange={(e) => setTo(e.target.value)} />}</Field></div>
            </div>
          )}
          <span className="ml-auto text-label text-ink-secondary">{fmtDate(dateFrom)}{dateFrom !== dateTo ? ` – ${fmtDate(dateTo)}` : ""}</span>
        </div>
      </Card>
      <MetricStrip items={[
        { label: "Tyres sold", value: units.toLocaleString(), tone: "accent" },
        { label: "Sales", value: sales.length },
        { label: "Different tyres", value: byTyre.length },
      ]} />
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <Card title="By tyre" padded={false}>
          <DataTable search={false} rows={data ? byTyre : null} rowKey={(r) => r.product_id} pageSize={20}
            empty="No sales in this period"
            columns={[
              { key: "p", header: "Tyre", cell: (r) => <ProductCell name={r.name} sku={r.sku} /> },
              { key: "u", header: "Sold", align: "right", cell: (r) => <span className="num font-semibold">{r.units}</span> },
            ]} />
        </Card>
        <Card title="Over time" padded={false}
          actions={<QuickFilters label="Group by" value={group} onChange={setGroup} options={[
            { id: "day", label: "Days" }, { id: "week", label: "Weeks" }, { id: "month", label: "Months" }]} />}>
          <DataTable search={false} rows={data ? byPeriod : null} rowKey={(r) => r.key} pageSize={31}
            empty="No sales in this period"
            columns={[
              { key: "p", header: group === "day" ? "Day" : group === "week" ? "Week" : "Month", cell: (r) => r.label },
              { key: "s", header: "Sales", align: "right", cell: (r) => r.sales },
              { key: "u", header: "Tyres", align: "right", cell: (r) => <span className="num font-semibold">{r.units}</span> },
            ]} />
        </Card>
      </div>
      <Card title="Sales in this period" className="mt-4" padded={false}>
        <DataTable mobile="cards" label="My sales" rows={data} rowKey={(s) => s.id} searchPlaceholder="Search sale or tyre…" empty="No sales in this period"
          columns={[
            { key: "n", mobile: "primary", header: "Sale", value: (s) => s.number, cell: (s) => <Link className="link" href={`/sales?sale=${s.id}`}>{s.number}</Link> },
            { key: "d", mobile: "field", mobileOrder: 1, header: "Date", value: (s) => s.sale_date, cell: (s) => fmtDate(s.sale_date) },
            { key: "t", mobile: "field", mobileOrder: 2, header: "Tyres", className: "min-w-64 whitespace-normal", value: (s) => s.lines.map((l) => `${l.sku} ${l.product_name}`).join(" "),
              cell: (s) => <div className="space-y-0.5 text-label">{s.lines.map((l) => <div key={l.id}>{l.chargeable_qty} × {l.product_name ?? l.sku} <span className="sku text-label text-ink-secondary">{l.sku}</span></div>)}</div> },
            { key: "q", mobile: "field", mobileOrder: 3, header: "Units", align: "right", value: (s) => s.total_qty, cell: (s) => s.total_qty },
            { key: "src", mobile: "status", header: "Source", value: (s) => s.source, cell: (s) => <Badge value={s.source} /> },
          ]} />
      </Card>
    </>
  );
}
