"use client";

/**
 * Journey-specific stock check (finding 7): only the tyres on this request, with plain answers —
 * is it in the warehouse, how many does this dealer already hold, could other dealers spare some?
 * Staff only (the API refuses dealers); no search box.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useProductIndex } from "./pickers";
import { Alert, Card, cx, ProductCell } from "./ui";
import { vocab } from "@/lib/terms";

export interface Availability {
  product_id: number;
  warehouse_available: number;
  warehouse_on_hand: number;
  at_this_location: { on_hand: number; available: number } | null;
  dealer_total_on_hand: number | null;
  other_dealers: { available: number; locations: number };
}

export function StockAvailability({ productIds, dealerLocationId, requested, title = "Stock for this request" }: {
  productIds: number[]; dealerLocationId?: number | null; requested?: Record<number, number>; title?: string;
}) {
  const { user } = useAuth();
  const { byId } = useProductIndex();
  const ids = [...new Set(productIds.filter(Boolean))];
  const key = `${ids.join(",")}|${dealerLocationId ?? ""}`;
  const [state, setState] = useState<{ key: string; rows: Availability[] | null; error: string | null }>({ key: "", rows: null, error: null });
  const staff = !!user && !user.reseller_id;

  useEffect(() => {
    if (!staff || !ids.length) return;
    let live = true;
    (async () => {
      try {
        const rows = await api.post<Availability[]>("/inventory/availability-check", { product_ids: ids, dealer_location_id: dealerLocationId ?? null });
        if (live) setState({ key, rows, error: null });
      } catch (e) {
        if (live) setState({ key, rows: null, error: e instanceof Error ? e.message : "Could not check stock" });
      }
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures ids and location
  }, [key, staff]);

  if (!staff || !ids.length) return null;
  const rows = state.key === key ? state.rows : null;
  return (
    <Card title={title} subtitle={`Only the ${vocab.items} on this request`} padded={false}>
      <Alert>{state.key === key ? state.error : null}</Alert>
      {!rows && !state.error && <div className="px-5 py-4 text-label text-ink-muted">Checking stock…</div>}
      {rows && (
        <ul className="divide-y divide-line">
          {rows.map((r) => {
            const want = requested?.[r.product_id];
            const enough = want === undefined ? r.warehouse_available > 0 : r.warehouse_available >= want;
            return (
              <li key={r.product_id} className="grid gap-x-6 gap-y-1 px-5 py-3 text-label sm:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]" data-testid="availability-row">
                <div className="min-w-0">
                  <ProductCell name={byId.get(r.product_id)?.display_name ?? `${vocab.Item} #${r.product_id}`} sku={byId.get(r.product_id)?.sku} />
                  {want !== undefined && <div className="text-caption text-ink-muted">Requested: <b className="num font-medium text-ink">{want}</b></div>}
                </div>
                <div>
                  <span className="text-ink-muted">Warehouse: </span>
                  {r.warehouse_available > 0
                    ? <b className={cx("font-semibold", enough ? "text-success" : "text-warning")}>Yes – {r.warehouse_available} available</b>
                    : <b className="font-semibold text-danger">No</b>}
                  {want !== undefined && r.warehouse_available > 0 && !enough && <div className="text-caption text-warning">Not enough for all {want}</div>}
                </div>
                <div>
                  {r.at_this_location
                    ? <><span className="text-ink-muted">Already at this {vocab.partner}: </span><b className="num font-medium">{r.at_this_location.on_hand}</b>
                        {r.dealer_total_on_hand !== null && r.dealer_total_on_hand !== r.at_this_location.on_hand &&
                          <span className="text-ink-muted"> (all {vocab.sites}: {r.dealer_total_on_hand})</span>}</>
                    : <span className="text-ink-muted">—</span>}
                </div>
                <div><span className="text-ink-muted">Other {vocab.partners}: </span><b className="num font-medium">{r.other_dealers.available}</b>
                  {r.other_dealers.locations > 0 && <span className="text-ink-muted"> at {r.other_dealers.locations} {vocab.site}{r.other_dealers.locations === 1 ? "" : "s"}</span>}</div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
