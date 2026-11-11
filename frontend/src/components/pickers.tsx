"use client";

import { Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api, withQuery } from "@/lib/api";
import { matchesSearch } from "@/lib/search";
import type { Location, Product, ResellerSummary } from "@/lib/types";
import { cx, Input, Select } from "./ui";

const cache = new Map<string, Promise<unknown>>();

/** Cached GET for reference data used by pickers. Call invalidate() after changing it. */
export function useReference<T>(path: string, query?: Record<string, string | number | boolean | string[]>) {
  const key = withQuery(path, query);
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    if (!cache.has(key)) cache.set(key, api.get<T>(path, query).catch((e) => { cache.delete(key); throw e; }));
    let alive = true;
    (cache.get(key) as Promise<T>).then((d) => alive && setData(d)).catch(() => alive && setData(null));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return data;
}

export function invalidateReference() {
  cache.clear();
}

export function useProducts() {
  return useReference<Product[]>("/products", { active: true, limit: 1000 });
}

/** Every product (active and inactive), indexed by id and SKU, so any screen can name a tyre from its SKU. */
export function useProductIndex() {
  const all = useReference<Product[]>("/products", { limit: 1000 });
  return useMemo(() => {
    const byId = new Map<number, Product>(), bySku = new Map<string, Product>();
    for (const p of all ?? []) { byId.set(p.id, p); bySku.set(p.sku, p); }
    return { byId, bySku, ready: all !== null };
  }, [all]);
}

/** "NORDWAY ECOTRAIL 195/65R15 91H" for a SKU or product id; falls back to the SKU while loading or if unknown. */
export function useTyreName() {
  const { byId, bySku } = useProductIndex();
  return (ref: { sku?: string | null; productId?: number | null }) => {
    const p = (ref.productId != null ? byId.get(ref.productId) : undefined) ?? (ref.sku ? bySku.get(ref.sku) : undefined);
    return p ? p.display_name : null;
  };
}

/** Tyres are always shown by model and size with the SKU, never by SKU alone (pilot feedback). */
export function TyreLabel({ sku, productId, qty, className }: { sku?: string | null; productId?: number | null; qty?: number; className?: string }) {
  const name = useTyreName()({ sku, productId });
  return (
    <span className={cx("inline", className)}>
      {qty !== undefined && <span className="num font-medium">{qty} × </span>}
      <span className="text-ink">{name ?? sku ?? "—"}</span>
      {sku && name && <span className="ml-1.5 sku text-label text-ink-secondary">{sku}</span>}
    </span>
  );
}

export function useLocations(types: string[]) {
  return useReference<Location[]>("/locations", { type: types, active: true });
}

/** How a shop is named everywhere (UAT round 2): the dealer's business name first, then the shop and city.
 *  "Roskill Tyres — Main shop (Auckland)"; a warehouse by its name. The code is never the main identifier. */
export function shopText(l: Pick<Location, "name" | "city" | "reseller_name">, withDealer = true) {
  // Don't repeat the dealer: a shop named "Roskill Tyres — Henderson" reads "Roskill Tyres — Henderson".
  const dealer = l.reseller_name?.trim() ?? "";
  const trimmed = dealer && l.name.trim().toLowerCase().startsWith(dealer.toLowerCase())
    ? l.name.trim().slice(dealer.length).replace(/^[\s—–\-,·]+/, "") : l.name;
  const shop = trimmed || null;
  const place = [shop, l.city && `(${l.city})`].filter(Boolean).join(" ");
  if (!withDealer || !l.reseller_name) return place || l.name;
  if (!shop) return [l.reseller_name, place].filter(Boolean).join(" ");
  return `${l.reseller_name} — ${place}`;
}

/** Every shop and warehouse, looked up by id or code, for tables that only carry the shop code. */
export function useShopIndex() {
  const all = useLocations(["CONSIGNMENT", "WAREHOUSE"]);
  return useMemo(() => {
    const byId = new Map<number, Location>(), byCode = new Map<string, Location>();
    for (const l of all ?? []) { byId.set(l.id, l); byCode.set(l.code, l); }
    return { byId, byCode };
  }, [all]);
}

/** Dealer name (main line) with shop, city and code underneath. Pass the dealer name when the row has it; a
 *  shop known only by code or id is looked up. withDealer=false for screens about one dealer. */
export function ShopLabel({ code, locationId, dealer, withDealer = true, inline = false }: {
  code?: string | null; locationId?: number | null; dealer?: string | null; withDealer?: boolean; inline?: boolean;
}) {
  const { byId, byCode } = useShopIndex();
  const l = (locationId != null ? byId.get(locationId) : undefined) ?? (code ? byCode.get(code) : undefined);
  const name = withDealer ? dealer ?? l?.reseller_name ?? null : null;
  const shop = l ? shopText(l, false) : null;
  const detail = [name ? shop : null, code ?? l?.code].filter(Boolean).join(" · ");
  if (inline) return <span>{name ?? shop ?? code ?? "—"}{detail && <span className="text-ink-secondary"> ({detail})</span>}</span>;
  return (
    <div className="min-w-0">
      <div className="truncate text-ink">{name ?? shop ?? code ?? "—"}</div>
      {detail && <div className="truncate text-caption text-ink-muted">{detail}</div>}
    </div>
  );
}

export function useResellers() {
  return useReference<ResellerSummary[]>("/resellers");
}

const productLabel = (p: Product) => `${p.sku} — ${p.display_name}`;
const MAX_RESULTS = 60;

/** Searchable exact-SKU product picker: one field — type part of the SKU, brand, pattern or size, then pick a match. */
export function ProductSelect({ id, value, onChange, required, disabled, placeholder = "Search SKU, brand or size…" }: {
  id?: string; value: number | ""; onChange: (id: number | "") => void; required?: boolean; disabled?: boolean; placeholder?: string;
}) {
  const products = useProducts();
  const autoId = useId();
  const inputId = id ?? `product-${autoId}`;
  const listId = `${inputId}-list`;
  const selected = useMemo(() => (products ?? []).find((p) => p.id === value) ?? null, [products, value]);
  const [query, setQuery] = useState<string | null>(null);   // null = not editing: show the selected product
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const matches = useMemo(() => {
    const all = products ?? [];
    // "195 65", "19565" and "195/65" all find 195/65R15: case, spaces and punctuation are ignored (lib/search).
    const hits = (query ?? "").trim() ? all.filter((p) => matchesSearch([p.sku, p.display_name, p.size_display], query ?? "")) : all;
    return hits.slice(0, MAX_RESULTS);
  }, [products, query]);

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function choose(p: Product) {
    onChange(p.id);
    setQuery(null);
    setOpen(false);
  }

  function close() {
    // Clearing the text and leaving the field clears the selection; otherwise keep the current product.
    if (query !== null && query.trim() === "") onChange("");
    setQuery(null);
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, matches.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && open) { e.preventDefault(); if (matches[active]) choose(matches[active]); }
    else if (e.key === "Escape") { if (open) { e.preventDefault(); close(); } }
  }

  const text = query ?? (selected ? productLabel(selected) : "");
  return (
    <div className="relative min-w-0 flex-1">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      <Input id={inputId} role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open && matches[active] ? `${listId}-${matches[active].id}` : undefined}
        aria-required={required || undefined} autoComplete="off" disabled={disabled}
        className={cx("pl-9", selected && query === null ? "pr-9" : "")} title={selected && query === null ? productLabel(selected) : undefined}
        placeholder={products ? placeholder : "Loading products…"} value={text}
        onFocus={(e) => { e.target.select(); setOpen(true); setActive(0); }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onBlur={close} onKeyDown={onKeyDown} />
      {selected && query === null && !disabled && (
        <button type="button" aria-label="Clear product" tabIndex={-1}
          onMouseDown={(e) => { e.preventDefault(); onChange(""); setQuery(""); setOpen(true); }}
          className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-ink-muted hover:bg-subtle hover:text-ink">
          <X className="size-3.5" aria-hidden />
        </button>
      )}
      {open && !disabled && (
        <ul id={listId} ref={listRef} role="listbox" aria-label="Products"
          className="absolute z-50 mt-1 max-h-64 w-full min-w-72 overflow-y-auto rounded-control border border-line bg-surface py-1 shadow-pop">
          {!products && <li className="px-3 py-2 text-label text-ink-muted">Loading…</li>}
          {products && matches.length === 0 && <li className="px-3 py-2 text-label text-ink-muted">No matching products</li>}
          {matches.map((p, i) => (
            <li key={p.id} id={`${listId}-${p.id}`} data-index={i} role="option" aria-selected={p.id === value}
              onMouseDown={(e) => { e.preventDefault(); choose(p); }} onMouseEnter={() => setActive(i)}
              className={cx("cursor-pointer px-3 py-1.5 text-label", i === active && "bg-neutral-soft", p.id === value && "font-medium")}>
              <span className="sku text-label text-ink">{p.sku}</span>
              <span className="text-ink-secondary"> — {p.display_name}</span>
            </li>
          ))}
          {products && matches.length === MAX_RESULTS && (
            <li className="px-3 py-1.5 text-caption text-ink-muted">Showing the first {MAX_RESULTS}; keep typing to narrow down.</li>
          )}
        </ul>
      )}
    </div>
  );
}

export function LocationSelect({ id, value, onChange, types, required, placeholder = "Select location…", exclude, disabled }: {
  id?: string; value: number | ""; onChange: (id: number | "") => void; types: string[]; required?: boolean;
  placeholder?: string; exclude?: number; disabled?: boolean;
}) {
  const locations = useLocations(types);
  return (
    <Select id={id} required={required} disabled={disabled} value={value}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
      placeholder={locations ? placeholder : "Loading…"}
      options={(locations ?? []).filter((l) => l.id !== exclude).map((l) => ({ value: l.id, label: `${shopText(l)} · ${l.code}` }))
        .sort((a, b) => a.label.localeCompare(b.label))} />
  );
}

export function ResellerSelect({ id, value, onChange, placeholder = "All dealers" }: {
  id?: string; value: number | ""; onChange: (id: number | "") => void; placeholder?: string;
}) {
  const resellers = useResellers();
  return (
    <Select id={id} aria-label={id ? undefined : "Dealer"} value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
      placeholder={placeholder}
      options={(resellers ?? []).map((r) => ({ value: r.id, label: `${r.account_ref} — ${r.business_name}` }))} />
  );
}
