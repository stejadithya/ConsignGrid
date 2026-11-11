"use client";

import { PackageSearch, Search } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Product, SourceOption } from "@/lib/types";
import { Alert, Button, DataTable, Field, Input, Modal, ProductCell, Qty } from "./ui";

interface Sources { warehouse_available: number; sources: SourceOption[] }

/** Where a tyre is: the warehouse and every dealer holding it (staff and Sales Reps; never shown to dealers).
 * Starts empty (finding 6): matches appear as you type, from 3 characters after a short pause, or on Search / Enter.
 * "195 65" finds 195/65R15. A deep link may pass the tyre to show. */
const TYPE_AHEAD_MIN = 3;
const TYPE_AHEAD_DELAY_MS = 300;

export function CheckStockPanel({ initialProduct }: { initialProduct?: number }) {
  const [text, setText] = useState("");
  const [matches, setMatches] = useState<Product[] | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [linked] = useState<number | "">(initialProduct ?? "");
  const search = useAction();
  const productId = product?.id ?? (matches === null ? linked : "");
  const { data, error } = useApi<Sources>(productId ? "/transfers/sources" : null, { product_id: productId });
  const { data: linkedProduct } = useApi<Product>(!product && matches === null && linked ? `/products/${linked}` : null);
  const p = product ?? linkedProduct ?? undefined;
  const rows = data ? [...data.sources].sort((a, b) => b.available - a.available || a.location_code.localeCompare(b.location_code)) : null;
  const atDealers = (data?.sources ?? []).reduce((a, s) => a + s.available, 0);

  const latest = useRef(0);   // only the newest search updates the results (typing fires several)
  const { run: runSearch } = search;
  async function find(q: string) {
    const ticket = ++latest.current;
    const found = await runSearch(() => api.get<Product[]>("/products", { q, active: true, limit: 50 }));
    if (!found || ticket !== latest.current) return;
    const exact = found.find((x) => x.sku.toLowerCase() === q.toLowerCase());
    setProduct(exact ?? (found.length === 1 ? found[0] : null));
    setMatches(found);
  }
  function run(e: FormEvent) {
    e.preventDefault();
    const q = text.trim();
    if (q) void find(q);
  }
  // Search as you type: from TYPE_AHEAD_MIN characters, once typing pauses.
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  function onType(value: string) {
    setText(value);
    setProduct(null);
    clearTimeout(timer.current);
    const q = value.trim();
    if (!q) setMatches(null);
    if (q.length >= TYPE_AHEAD_MIN) timer.current = setTimeout(() => void find(q), TYPE_AHEAD_DELAY_MS);
  }

  return (
    <div className="space-y-4">
      <form onSubmit={run} className="flex flex-wrap items-end gap-2" role="search">
        <div className="min-w-60 flex-1">
          <Field label="Tyre" hint="SKU, size, brand or pattern. Matches appear as you type (3 characters or more).">
            {(id) => <Input id={id} value={text} onChange={(e) => onType(e.target.value)} placeholder="e.g. 700001 or 205 55 16" autoComplete="off" />}
          </Field>
        </div>
        <Button type="submit" variant="primary" disabled={!text.trim() || search.busy}><Search aria-hidden />{search.busy ? "Searching…" : "Search"}</Button>
      </form>
      <Alert>{search.error ?? error}</Alert>
      {matches && matches.length === 0 && <Alert tone="info">No tyre matches “{text.trim()}”.</Alert>}
      {matches && matches.length > 1 && !product && (
        <div className="overflow-hidden rounded-control border border-line">
          <div className="border-b border-line bg-subtle px-3 py-2 text-caption font-medium text-ink-secondary">{matches.length} tyres match — pick one</div>
          <ul className="max-h-72 divide-y divide-line overflow-y-auto">
            {matches.map((m) => (
              <li key={m.id}>
                <button type="button" onClick={() => setProduct(m)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-subtle">
                  <ProductCell name={m.display_name} sku={m.sku} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {productId && data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-control border border-line p-3">
              <div className="text-caption text-ink-muted">Main warehouse · available</div>
              <div className="num text-metric-compact font-semibold"><Qty value={data.warehouse_available} zeroMuted={false} tone={data.warehouse_available ? "ok" : "danger"} /></div>
            </div>
            <div className="rounded-control border border-line p-3">
              <div className="text-caption text-ink-muted">At dealers · available</div>
              <div className="num text-metric-compact font-semibold">{atDealers}</div>
              <div className="text-caption text-ink-muted">{data.sources.length} dealer location(s) hold {p?.display_name ?? "it"}</div>
            </div>
          </div>
          <DataTable mobile="cards" label="Dealers holding this tyre" search={false} rows={rows} rowKey={(s) => s.location_id}
            empty="No dealer holds this tyre" emptyHint="Only the warehouse figure above applies."
            columns={[
              { key: "d", mobile: "primary", header: "Dealer", cell: (s) => <div><div className="font-medium">{s.reseller_name}</div><div className="text-caption text-ink-muted">{s.location_code} · {s.location_name}</div></div> },
              { key: "a", mobile: "field", mobileOrder: 1, header: "Available", align: "right", cell: (s) => <span className="text-body-lg font-semibold"><Qty value={s.available} zeroMuted={false} /></span> },
              { key: "h", mobile: "field", mobileOrder: 2, header: "On hand", align: "right", cell: (s) => <Qty value={s.on_hand} /> },
              { key: "r", header: "Held back", align: "right", cell: (s) => <span title="Reserved or blocked"><Qty value={s.reserved + s.blocked} tone="warn" /></span> },
              { key: "t", mobile: "status", header: "Can transfer?", cell: (s) => s.eligible
                ? <span className="text-caption text-success">Yes</span>
                : <span className="text-caption text-ink-muted">{s.ineligible_reason}</span> },
            ]} />
          <p className="text-caption text-ink-muted">Available = on hand minus reserved and blocked. Dealers never see this list.</p>
        </>
      )}
    </div>
  );
}

/** The generic Check stock button: always opens empty (journey screens use StockAvailability instead). */
export function CheckStockButton({ size = "md" }: { size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size={size} onClick={() => setOpen(true)}><PackageSearch aria-hidden />Check stock</Button>
      {open && <Modal open wide title="Check stock" description="Where a tyre is right now: the warehouse and each dealer." onClose={() => setOpen(false)}>
        <CheckStockPanel />
      </Modal>}
    </>
  );
}
