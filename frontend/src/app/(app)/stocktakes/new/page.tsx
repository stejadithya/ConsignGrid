"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ProductSelect, ResellerSelect, useLocations } from "@/components/pickers";
import { StocktakeHeader } from "@/components/StocktakeHeader";
import { Alert, Button, Card, Field, Input, MobileActionBar, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { todayIso } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { AllocationPosition, Reseller, Stocktake } from "@/lib/types";

interface CountLine { product: number | ""; sku?: string; name?: string; counted: string; damaged: string }

/** Mobile-friendly count capture. Expected quantities are hidden to avoid anchoring the count. */
export default function NewStocktakePage() {
  const params = useSearchParams();
  const router = useRouter();
  const [location, setLocation] = useState<number | "">(params.get("location") ? Number(params.get("location")) : "");
  // Choose the dealer first (name or account ref), then the shop (finding 27).
  const [picked, setDealer] = useState<number | "">(params.get("reseller") ? Number(params.get("reseller")) : "");
  const allShops = useLocations(["CONSIGNMENT"]);
  const dealerId = picked || (location ? allShops?.find((l) => l.id === location)?.reseller_id : null) || "";
  const { data: dealer } = useApi<Reseller>(dealerId ? `/resellers/${dealerId}` : null);
  const shops = (dealer?.locations ?? []).filter((l) => l.type === "CONSIGNMENT" && l.is_active);
  const shopId = location || (shops.length === 1 ? shops[0].id : "");
  const shop = shops.find((l) => l.id === shopId);
  const [date, setDate] = useState(todayIso());
  const [notes, setNotes] = useState("");
  // Known SKUs come from the location's allocations/stock; `edits` holds what the counter typed.
  const [edits, setEdits] = useState<Record<number, CountLine>>({});
  const [extras, setExtras] = useState<CountLine[]>([]);
  const { data: positions } = useApi<AllocationPosition[]>(shopId ? "/allocations/positions" : null, { location_id: shopId });
  const action = useAction();
  const known: CountLine[] = (positions ?? []).map((p) => edits[p.product_id] ?? { product: p.product_id, sku: p.sku, name: p.product_name, counted: "", damaged: "0" });
  const lines = [...known, ...extras];
  const setLines = (update: (ls: CountLine[]) => CountLine[]) => {
    const next = update(lines);
    const nextEdits: Record<number, CountLine> = {};
    next.slice(0, known.length).forEach((l) => { if (l.product) nextEdits[l.product] = l; });
    setEdits(nextEdits);
    setExtras(next.slice(known.length));
  };
  const changeLocation = (v: number | "") => { setLocation(v); setEdits({}); setExtras([]); };
  const changeDealer = (v: number | "") => { setDealer(v); changeLocation(""); };

  async function save(submit: boolean) {
    const st = await action.run(async () => {
      const created = await api.post<Stocktake>("/stocktakes", {
        location_id: shopId, count_date: date, notes: notes || null,
        counts: lines.filter((l) => l.product && l.counted !== "").map((l) => ({ product_id: l.product, counted_qty: Number(l.counted), counted_damaged_qty: Number(l.damaged || 0) })),
      });
      return submit ? api.post<Stocktake>(`/stocktakes/${created.id}/submit`) : created;
    });
    if (st) router.push(`/stocktakes/${st.id}`);
  }

  return (
    <>
      <PageHeader title="New stocktake" subtitle="Count what is physically on the shelf, including damaged tyres. SKUs in stock but not counted are treated as zero on submission." />
      <Alert>{action.error}</Alert>
      <Card className="max-w-3xl">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Dealer" required hint="Search by name or account reference">{(id) => <ResellerSelect id={id} value={dealerId} onChange={changeDealer} placeholder="Choose the dealer…" />}</Field>
          <Field label="Shop" required>{(id) => <Select id={id} value={shopId} disabled={!dealer} onChange={(e) => changeLocation(e.target.value ? Number(e.target.value) : "")}
            placeholder={dealer ? "Choose the shop…" : "Choose the dealer first"}
            options={shops.map((l) => ({ value: l.id, label: `${l.name} — ${[l.address_line1, l.city].filter(Boolean).join(", ") || l.code}` }))} />}</Field>
          <Field label="Count date" required>{(id) => <Input id={id} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
        </div>
        {dealer && shop && <div className="mt-4"><StocktakeHeader dealer={dealer.business_name} accountRef={dealer.account_ref} shop={shop.name} code={shop.code}
          address={[shop.address_line1, shop.address_line2].filter(Boolean).join(", ") || null} city={shop.city} rep={dealer.sales_rep_name} /></div>}
        {shopId !== "" && (
          <div className="mt-4 space-y-2">
            <div className="grid grid-cols-[1fr_80px_80px] gap-2 text-caption font-medium text-ink-secondary"><span>Product</span><span>Counted</span><span>Of which damaged</span></div>
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[1fr_80px_80px] items-center gap-2">
                {l.sku ? <div className="text-body"><span className="sku text-label">{l.sku}</span><div className="text-caption text-ink-muted">{l.name}</div></div>
                  : <ProductSelect value={l.product} onChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, product: v } : x)))} />}
                <Input type="number" inputMode="numeric" min={0} aria-label={`Counted ${l.sku ?? ""}`} value={l.counted} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, counted: e.target.value } : x)))} />
                <Input type="number" inputMode="numeric" min={0} aria-label={`Damaged ${l.sku ?? ""}`} value={l.damaged} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, damaged: e.target.value } : x)))} />
              </div>
            ))}
            <Button size="sm" onClick={() => setLines((ls) => [...ls, { product: "", counted: "", damaged: "0" }])}>Add another SKU</Button>
          </div>
        )}
        <div className="mt-4"><Field label="Notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field></div>
        <div className="mt-4">
          <MobileActionBar align="start">
            <Button disabled={action.busy || !shopId} onClick={() => save(false)}>Save draft</Button>
            <Button variant="primary" disabled={action.busy || !shopId} onClick={() => save(true)}>Submit count</Button>
          </MobileActionBar>
        </div>
      </Card>
    </>
  );
}
