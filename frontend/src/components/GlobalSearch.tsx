"use client";

import { Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Badge, cx } from "./ui";

/** One result from GET /search. */
export interface SearchHit {
  type: string; label: string; id: number; title: string; subtitle: string | null; status: string | null;
  when: string | null; href: string; exact: boolean;
}
export interface SearchResults { query: string; documents: SearchHit[]; dealers: SearchHit[]; tyres: SearchHit[]; people: SearchHit[] }

const MIN = 3;
const DELAY_MS = 300;
const GROUPS: [keyof Omit<SearchResults, "query">, string][] = [["documents", "Documents"], ["dealers", "Dealers"], ["tyres", "Tyres"], ["people", "People"]];

export const flatten = (r: SearchResults | null) => (r ? GROUPS.flatMap(([k]) => r[k]) : []);

/** One search box for the whole app: document numbers (SRQ-, REP-, TRF-, DEL-, SAL-, INV-, PO-, GRN-, STK-, TXN-, and the
 *  Xero number for those allowed), dealers, tyres and people. Results come as you type; Enter on an exact number opens
 *  it. Everyone only finds what they could already open (the API scopes it). Press "/" anywhere to start typing. */
export function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [open, setOpen] = useState(false);          // results showing
  const [phone, setPhone] = useState(false);        // full-width search on small screens
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(0);
  const listId = useId();
  const hits = flatten(results);

  // "/" focuses the search, unless someone is typing in a field already.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      e.preventDefault();
      setPhone(window.innerWidth < 640);
      setTimeout(() => input.current?.focus(), 0);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // Close when clicking elsewhere.
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function onType(value: string) {
    setQ(value);
    setActive(-1);
    if (timer.current) clearTimeout(timer.current);
    if (value.replace(/[^\p{L}\p{N}]/gu, "").length < MIN) { setResults(null); setBusy(false); return; }
    setBusy(true);
    timer.current = setTimeout(async () => {
      const ticket = ++latest.current;
      try {
        const r = await api.get<SearchResults>("/search", { q: value });
        if (ticket === latest.current) { setResults(r); setOpen(true); }
      } finally {
        if (ticket === latest.current) setBusy(false);
      }
    }, DELAY_MS);
  }

  function go(hit: SearchHit) {
    setOpen(false); setPhone(false); setQ(""); setResults(null); setActive(-1);
    router.push(hit.href);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && hits.length) { e.preventDefault(); setOpen(true); setActive((a) => (a + 1) % hits.length); }
    else if (e.key === "ArrowUp" && hits.length) { e.preventDefault(); setActive((a) => (a <= 0 ? hits.length - 1 : a - 1)); }
    else if (e.key === "Enter") {
      const pick = active >= 0 ? hits[active] : hits.find((h) => h.exact) ?? (hits.length === 1 ? hits[0] : undefined);
      if (pick) { e.preventDefault(); go(pick); }
    } else if (e.key === "Escape") { setOpen(false); setPhone(false); input.current?.blur(); }
  }

  const showing = open && q.replace(/[^\p{L}\p{N}]/gu, "").length >= MIN && results !== null;
  // Position of each group's first result in the keyboard order.
  const starts = GROUPS.map((_, gi) => GROUPS.slice(0, gi).reduce((a, [k]) => a + (results?.[k].length ?? 0), 0));
  const panel = showing && (
    <div id={listId} role="listbox" aria-label="Search results"
      className="absolute top-full right-0 left-0 z-50 mt-1 max-h-[70vh] overflow-y-auto rounded-card border border-line bg-surface py-1 shadow-lg sm:w-[30rem] sm:left-auto">
      {hits.length === 0 && <div className="px-3 py-3 text-label text-ink-muted">Nothing found for “{q}”. Try a number such as SRQ-000123, a dealer, or a tyre size like 195 65.</div>}
      {GROUPS.map(([key, title], gi) => results![key].length > 0 && (
        <div key={key} role="group" aria-label={title}>
          <div className="px-3 pt-2 pb-1 text-caption font-semibold tracking-wide text-ink-muted uppercase">{title}</div>
          {results![key].map((h, j) => {
            const i = starts[gi] + j;
            return (
              <div key={`${h.type}-${h.id}`} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()} onClick={() => go(h)} onMouseEnter={() => setActive(i)}
                className={cx("flex cursor-pointer items-start justify-between gap-3 px-3 py-2", i === active && "bg-neutral-soft")}>
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><span className="truncate text-body font-medium text-ink">{h.title}</span>
                    <span className="shrink-0 text-caption text-ink-muted">{h.label}</span></div>
                  {(h.subtitle || h.when) && <div className="truncate text-caption text-ink-secondary">{[h.subtitle, h.when && fmtDate(h.when)].filter(Boolean).join(" · ")}</div>}
                </div>
                {h.status && <Badge value={h.status} />}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );

  const field = (
    <div className="relative w-full">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      <input ref={input} type="search" role="combobox" aria-label="Search everything" aria-expanded={!!showing} aria-controls={listId}
        aria-autocomplete="list" aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        placeholder="Search numbers, dealers, tyres…" value={q} autoComplete="off" spellCheck={false}
        onChange={(e) => onType(e.target.value)} onFocus={() => results && setOpen(true)} onKeyDown={onKeyDown}
        className="h-9 w-full rounded-control border border-line bg-subtle pr-9 pl-9 text-body text-ink placeholder:text-ink-muted focus:border-ink focus:bg-surface focus:outline-none" />
      {busy ? <span className="absolute top-1/2 right-3 size-3.5 -translate-y-1/2 animate-spin rounded-full border-2 border-line border-t-ink" aria-hidden />
        : <kbd className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 rounded border border-line px-1.5 text-caption text-ink-muted sm:block">/</kbd>}
    </div>
  );

  return (
    <div ref={box} className="relative min-w-0 sm:w-72 lg:w-96">
      {/* Phones: an icon that opens a full-width search across the top. */}
      <button type="button" className="touch-target rounded-md p-1.5 text-ink-secondary hover:bg-subtle sm:hidden" aria-label="Search"
        onClick={() => { setPhone(true); setTimeout(() => input.current?.focus(), 0); }}>
        <Search className="size-5" aria-hidden />
      </button>
      <div className={cx(phone ? "fixed inset-x-0 top-0 z-50 flex items-center gap-2 border-b border-line bg-surface p-2 sm:static sm:border-0 sm:p-0"
        : "hidden sm:block")}>
        {field}
        {phone && <button type="button" className="touch-target rounded-md p-1.5 text-ink-secondary sm:hidden" aria-label="Close search" onClick={() => { setPhone(false); setOpen(false); }}><X className="size-5" aria-hidden /></button>}
        {panel}
      </div>
    </div>
  );
}
