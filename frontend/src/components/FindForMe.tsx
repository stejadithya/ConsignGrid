"use client";

import { Check, HeartHandshake } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "./ui";

/*
 * "Get this tyre for me". When the warehouse cannot cover a tyre on a stock request, the requester sees a kind
 * note instead of "out of stock". On submission the warehouse arranges the tyre from another dealer who holds it.
 * Wording is deliberately warm and never mentions stock levels.
 */

export const FIND_TITLE = "Leave this one with us";
export const FIND_TEXT = "We're arranging this tyre for you and will let you know as soon as it's on its way.";

/** Which tyres need the warehouse's help. Asks only yes / no (no stock figures), and only after typing settles. */
export function useNeedsHelp(lines: { product: number | ""; qty: string }[]): Set<number> {
  const wanted = useMemo(() => lines
    .filter((l) => l.product !== "" && Number.isInteger(Number(l.qty)) && Number(l.qty) > 0)
    .map((l) => ({ product_id: Number(l.product), quantity: Number(l.qty) })), [lines]);
  const key = JSON.stringify(wanted);
  const [result, setResult] = useState<{ key: string; ids: Set<number> }>({ key: "", ids: new Set() });
  useEffect(() => {
    if (!wanted.length) return;
    let alive = true;
    const timer = setTimeout(() => {
      api.post<{ product_id: number; needs_help: boolean }[]>("/stock-requests/supply-check", { lines: wanted })
        .then((res) => alive && setResult({ key, ids: new Set(res.filter((x) => x.needs_help).map((x) => x.product_id)) }))
        .catch(() => undefined);   // the note is a courtesy; the request works without it
    }, 400);
    return () => { alive = false; clearTimeout(timer); };
    // `key` captures the lines being checked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return result.key === key ? result.ids : new Set();
}

/** The gentle note under a request line, with the "Get this tyre for me" button. */
export function FindForMeNote({ chosen, onChange }: { chosen: boolean; onChange: (chosen: boolean) => void }) {
  return (
    <div role="status" className="flex flex-wrap items-start gap-3 rounded-control border border-info-line bg-info-soft px-3.5 py-3 sm:col-span-full">
      <HeartHandshake className="mt-0.5 size-5 shrink-0 text-info" aria-hidden />
      <div className="min-w-0 flex-1 basis-56">
        {chosen ? (
          <>
            <p className="flex items-center gap-1.5 font-medium text-ink"><Check className="size-4 text-success" aria-hidden />Thank you! Our team is on it.</p>
            <p className="text-label text-ink-secondary">{FIND_TEXT}</p>
          </>
        ) : (
          <>
            <p className="font-medium text-ink">{FIND_TITLE}</p>
            <p className="text-label text-ink-secondary">{FIND_TEXT}</p>
          </>
        )}
      </div>
      {chosen
        ? <button type="button" className="self-center text-caption text-ink-muted underline underline-offset-4 hover:text-ink" onClick={() => onChange(false)}>Undo</button>
        : <Button size="sm" variant="primary" className="ml-8 self-center sm:ml-0" onClick={() => onChange(true)}>Get this tyre for me</Button>}
    </div>
  );
}

/** On a submitted request: the part of a line the warehouse is arranging, in the same warm words. */
export function ArrangingNote() {
  return (
    <div className="mt-1.5 flex items-start gap-2 rounded-md border border-info-line bg-info-soft px-2.5 py-2 text-caption">
      <HeartHandshake className="mt-px size-4 shrink-0 text-info" aria-hidden />
      <span><b className="font-medium text-ink">{FIND_TITLE}.</b> <span className="text-ink-secondary">{FIND_TEXT}</span></span>
    </div>
  );
}
