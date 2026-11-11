"use client";

import { Info } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";

interface Arrival { on: string; qty: number; reason: string; group: string; reference: string | null }
interface Origin { on_hand: number; arrivals: Arrival[]; more: boolean; in_stock: { label: string; qty: number }[] }

// Loaded only when someone opens an ⓘ, then kept for a minute so moving back and forth costs nothing.
const cache = new Map<string, { at: number; value: Promise<Origin> }>();
function load(locationId: number, productId: number): Promise<Origin> {
  const key = `${locationId}:${productId}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < 60_000) return hit.value;
  const value = api.get<Origin>("/inventory/provenance", { location_id: locationId, product_id: productId });
  value.catch(() => cache.delete(key));
  cache.set(key, { at: Date.now(), value });
  return value;
}

const tyres = (n: number) => `${n} ${n === 1 ? "tyre" : "tyres"}`;

/** ⓘ next to a SKU: hover (or tap) for a two-line summary of where this stock came from. */
export function StockOrigin({ locationId, productId }: { locationId: number | null | undefined; productId: number | null | undefined }) {
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top?: number; bottom?: number; left: number } | null>(null);
  const [data, setData] = useState<Origin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  const show = () => {
    if (!locationId || !productId) return;
    const r = button.current?.getBoundingClientRect();
    if (r) {
      const left = Math.max(8, Math.min(r.left - 12, window.innerWidth - 328));
      // Open upwards when the ⓘ is near the bottom of the screen.
      setPos(r.bottom + 220 > window.innerHeight ? { bottom: window.innerHeight - r.top + 6, left } : { top: r.bottom + 6, left });
    }
    setOpen(true);
    load(locationId, productId).then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load"));
  };
  const hide = () => { setOpen(false); setPinned(false); setAll(false); };
  const later = (fn: () => void, ms: number) => { clearTimeout(timer.current); timer.current = setTimeout(fn, ms); };

  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => {
      if (!button.current?.contains(e.target as Node) && !panel.current?.contains(e.target as Node)) hide();
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && hide();
    const scrolled = (e: Event) => !panel.current?.contains(e.target as Node) && hide();
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    window.addEventListener("scroll", scrolled, true);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("scroll", scrolled, true);
    };
  }, [open]);
  useEffect(() => () => clearTimeout(timer.current), []);

  if (!locationId || !productId) return null;
  const latest = data?.arrivals[0];
  return (
    <>
      <button ref={button} type="button" aria-label="Where this stock came from" aria-expanded={open}
        className="inline-flex size-5 shrink-0 items-center justify-center rounded-full text-ink-muted hover:text-ink focus-visible:text-ink"
        onClick={(e) => { e.stopPropagation(); if (pinned) hide(); else { show(); setPinned(true); } }}
        onMouseEnter={() => later(show, 200)}
        onMouseLeave={() => !pinned && later(hide, 150)}
        onFocus={show}
        onBlur={(e) => !pinned && !panel.current?.contains(e.relatedTarget as Node) && hide()}>
        <Info className="size-3.5" aria-hidden />
      </button>
      {open && pos && createPortal(
        <div ref={panel} role="tooltip" style={pos}
          className="fixed z-50 max-h-[60vh] w-80 overflow-y-auto rounded-control border border-line bg-surface p-3 text-left text-label leading-snug font-normal whitespace-normal text-ink shadow-lg"
          onMouseEnter={() => clearTimeout(timer.current)} onMouseLeave={() => !pinned && later(hide, 150)}
          onClick={(e) => e.stopPropagation()}>
          {error ? <p className="text-danger">{error}</p>
            : !data ? <p className="text-ink-muted">Loading…</p>
            : !latest ? <p className="text-ink-secondary">No tyres received here in the last 12 months.</p>
            : (
              <>
                {(all ? data.arrivals : [latest]).map((a, i) => (
                  <div key={i} className={i ? "mt-2 border-t border-line pt-2" : undefined}>
                    <p className="font-semibold">{tyres(a.qty)} received on {fmtDate(a.on)}{a.reference ? ` · ${a.reference}` : ""}</p>
                    <p className="text-ink-secondary">{a.reason}.</p>
                  </div>
                ))}
                {!all && data.in_stock.length > 1 && (
                  <p className="mt-2 text-caption text-ink-muted">
                    In stock now: {data.in_stock.map((p) => `${p.qty} ${p.label}`).join(" · ")}
                  </p>
                )}
                {data.arrivals.length > 1 && (
                  <button type="button" className="mt-2 text-caption font-medium text-ink underline decoration-brand decoration-2 underline-offset-4"
                    onClick={() => { setPinned(true); setAll((v) => !v); }}>
                    {all ? "Show less" : `Show all ${data.arrivals.length}${data.more ? "+" : ""} arrivals`}
                  </button>
                )}
              </>
            )}
        </div>,
        document.body,
      )}
    </>
  );
}
