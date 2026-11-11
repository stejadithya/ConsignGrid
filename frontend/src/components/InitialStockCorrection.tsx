"use client";

import { History, PencilLine, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { InitialStockCorrection, InitialStockEntry, StockCorrectionRow } from "@/lib/types";
import { ProductSelect, ShopLabel } from "./pickers";
import { Alert, Button, Card, DataTable, Field, Input, Loading, Modal, ProductCell, Textarea } from "./ui";

const changeWords = (c: InitialStockCorrection["changes"][number]) => `${c.sku} ${c.before} → ${c.after}`;

/** Initial stock entries with their corrections, and the Correct button (Relationship Manager and Administrator). */
export function InitialStockCorrections({ resellerId, onCorrected }: { resellerId: number; onCorrected?: () => void }) {
  const { data, error, reload } = useApi<InitialStockEntry[]>(`/resellers/${resellerId}/initial-stock/entries`);
  const [editing, setEditing] = useState<InitialStockEntry | null>(null);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  if (!data.length) return null;
  return (
    <>
      {data.map((e) => (
        <Card key={e.transaction_id} padded={false} title={<>Initial stock {e.transaction_number} · <ShopLabel inline code={e.location_code} withDealer={false} /></>}
          subtitle={<>Entered {fmtDateTime(e.recorded_at)}{e.recorded_by && ` by ${e.recorded_by}`}
            {e.can_correct && e.correctable_until && ` · Can be corrected until ${fmtDate(e.correctable_until)} or the first stock check`}</>}
          actions={<Button size="sm" disabled={!e.can_correct} onClick={() => setEditing(e)}><PencilLine aria-hidden />Correct initial stock</Button>}>
          {!e.can_correct && e.locked_reason && <div className="px-4 pt-3 text-caption text-ink-secondary">{e.locked_reason}</div>}
          <DataTable mobile="cards" label={`Initial stock ${e.transaction_number}`} search={false} rows={e.lines} rowKey={(l) => l.product_id}
            columns={[
              { key: "t", mobile: "primary", header: "Tyre", className: "min-w-48 whitespace-normal", cell: (l) => <ProductCell name={l.name} sku={l.sku} /> },
              { key: "r", mobile: "field", header: "Entered", align: "right", cell: (l) => l.recorded },
              { key: "c", mobile: "field", header: "Now", align: "right",
                cell: (l) => <span className={l.current !== l.recorded ? "font-semibold" : undefined}>{l.current}</span> },
            ]} />
          {e.corrections.length > 0 && (
            <div className="border-t border-line px-4 py-3">
              <div className="mb-2 flex items-center gap-1.5 text-label font-semibold"><History className="size-4" aria-hidden />Corrections</div>
              <ul className="space-y-2">
                {e.corrections.map((c) => (
                  <li key={c.transaction_id} className="text-label">
                    <div><span className="font-medium">{fmtDateTime(c.corrected_at)}</span>
                      {c.corrected_by && <span className="text-ink-secondary"> · {c.corrected_by}</span>}
                      <span className="text-ink-secondary"> · {c.transaction_number}</span></div>
                    <div className="sku">{c.changes.map(changeWords).join("; ")}</div>
                    <div className="text-ink-secondary">Reason: {c.reason}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      ))}
      {editing && <CorrectInitialStockModal resellerId={resellerId} entry={editing} onClose={() => setEditing(null)}
        onDone={() => { setEditing(null); reload(); onCorrected?.(); }} />}
    </>
  );
}

interface Added { product: number | ""; qty: string }

/** Set the correct quantity for each tyre on the entry (0 removes it), add missed tyres, and say what was wrong. */
export function CorrectInitialStockModal({ resellerId, entry, onClose, onDone }: {
  resellerId: number; entry: InitialStockEntry; onClose: () => void; onDone: () => void;
}) {
  const [qty, setQty] = useState<Record<number, string>>(() => Object.fromEntries(entry.lines.map((l) => [l.product_id, String(l.current)])));
  const [added, setAdded] = useState<Added[]>([]);
  const [reason, setReason] = useState("");
  const action = useAction();

  const changes = entry.lines.flatMap((l) => {
    const raw = qty[l.product_id];
    const after = raw === "" ? NaN : Number(raw);
    return Number.isInteger(after) && after !== l.current ? [{ l, after }] : [];
  });
  const tooLow = entry.lines.filter((l) => { const n = Number(qty[l.product_id]); return Number.isInteger(n) && n < l.current - l.free_now; });
  const invalid = entry.lines.some((l) => { const n = Number(qty[l.product_id]); return qty[l.product_id] === "" || !Number.isInteger(n) || n < 0; });
  const newLines = added.filter((a) => a.product !== "" && Number(a.qty) > 0);
  const duplicate = newLines.some((a, i) => entry.lines.some((l) => l.product_id === a.product) || newLines.findIndex((b) => b.product === a.product) !== i);
  const count = changes.length + newLines.length;
  const ready = count > 0 && !invalid && !tooLow.length && !duplicate && reason.trim().length >= 5;

  const save = async () => {
    const lines = [...changes.map(({ l, after }) => ({ product_id: l.product_id, quantity: after })),
      ...newLines.map((a) => ({ product_id: Number(a.product), quantity: Number(a.qty) }))];
    if (await action.run(() => api.post(`/resellers/${resellerId}/initial-stock/${entry.transaction_id}/corrections`, { lines, reason: reason.trim() }))) onDone();
  };

  return (
    <Modal open wide title={`Correct initial stock ${entry.transaction_number}`} onClose={onClose}
      description={<>The original entry is kept. Your correction is recorded next to it, with your name and reason, and the
        Administrator and Finance are told. Tyres already sold, reserved or blocked can&apos;t be corrected away.</>}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!ready || action.busy} onClick={save}>
          {action.busy ? "Saving…" : `Save correction${count ? ` (${count} tyre${count === 1 ? "" : "s"})` : ""}`}</Button></>}>
      <Alert>{action.error}</Alert>
      <div className="space-y-3">
        {entry.lines.map((l) => {
          const min = Math.max(0, l.current - l.free_now);
          const low = tooLow.includes(l);
          return (
            <div key={l.product_id} className="grid grid-cols-[1fr_7rem] items-start gap-3 max-sm:grid-cols-1">
              <div><ProductCell name={l.name} sku={l.sku} />
                <div className="text-caption text-ink-secondary">Entered {l.recorded} · now {l.current}{min > 0 && ` · at least ${min} (sold, reserved or blocked)`}</div></div>
              <Field label="Correct quantity" error={low ? `At least ${min}` : undefined}>
                {(id, describedBy) => <Input id={id} aria-describedby={describedBy} type="number" min={min} inputMode="numeric"
                  aria-label={`Correct quantity for ${l.sku}`} value={qty[l.product_id]}
                  onChange={(ev) => setQty({ ...qty, [l.product_id]: ev.target.value })} />}
              </Field>
            </div>
          );
        })}
        {added.map((a, i) => (
          <div key={i} className="grid grid-cols-[1fr_7rem_auto] items-center gap-2">
            <ProductSelect value={a.product} onChange={(v) => setAdded(added.map((x, j) => (j === i ? { ...x, product: v } : x)))} />
            <Input type="number" min={1} aria-label={`Quantity for added tyre ${i + 1}`} placeholder="Qty" value={a.qty}
              onChange={(ev) => setAdded(added.map((x, j) => (j === i ? { ...x, qty: ev.target.value } : x)))} />
            <Button variant="ghost" aria-label={`Remove added tyre ${i + 1}`} onClick={() => setAdded(added.filter((_, j) => j !== i))}><Trash2 aria-hidden /></Button>
          </div>
        ))}
        {duplicate && <p className="text-caption text-danger">That tyre is already on this entry: change its quantity above instead.</p>}
        <Button size="sm" onClick={() => setAdded([...added, { product: "", qty: "" }])}><Plus aria-hidden />Add a missed tyre</Button>
        <Field label="What was wrong?" required hint="At least 5 characters. Kept with the correction for audits.">
          {(id, describedBy) => <Textarea id={id} aria-describedby={describedBy} rows={2} value={reason} onChange={(ev) => setReason(ev.target.value)}
            placeholder="e.g. Typed 12 instead of 2 while serving a customer" />}
        </Field>
        {count > 0 && (
          <div className="rounded-control bg-neutral-soft px-3 py-2 text-label">
            <span className="font-semibold">You are changing: </span>
            {[...changes.map(({ l, after }) => `${l.sku} ${l.current} → ${after}`), ...newLines.map((a) => `new tyre +${a.qty}`)].join("; ")}
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Reports → Stock corrections: every initial stock correction, one row per tyre changed. */
export function StockCorrectionsReport() {
  const { data, error } = useApi<{ rows: StockCorrectionRow[]; corrections: number }>("/reports/stock-corrections");
  return (
    <>
      <Alert>{error}</Alert>
      <Card padded={false} title="Initial stock corrections" subtitle={data ? `${data.corrections} correction${data.corrections === 1 ? "" : "s"}` : undefined}>
        <DataTable label="Stock corrections" rows={data?.rows} rowKey={(r) => `${r.transaction_number}-${r.sku}`} pageSize={100}
          empty="No corrections" emptyHint="Corrections to a dealer's initial stock appear here."
          columns={[
            { key: "d", header: "When", value: (r) => r.corrected_at, cell: (r) => fmtDateTime(r.corrected_at) },
            { key: "dl", header: "Dealer", value: (r) => r.reseller_name ?? "",
              cell: (r) => r.reseller_id ? <Link className="link" href={`/resellers/${r.reseller_id}`}>{r.reseller_name}</Link> : "—" },
            { key: "s", header: "Shop", value: (r) => r.location_code ?? "", cell: (r) => <ShopLabel code={r.location_code} withDealer={false} /> },
            { key: "k", header: "SKU", value: (r) => r.sku, cell: (r) => <span className="sku text-label">{r.sku}</span> },
            { key: "b", header: "Before", align: "right", value: (r) => r.before, cell: (r) => r.before },
            { key: "a", header: "After", align: "right", value: (r) => r.after, cell: (r) => r.after },
            { key: "c", header: "Change", align: "right", value: (r) => r.change, cell: (r) => (r.change > 0 ? `+${r.change}` : r.change) },
            { key: "by", header: "By", value: (r) => r.corrected_by ?? "", cell: (r) => r.corrected_by ?? "—" },
            { key: "why", header: "Reason", className: "min-w-56 whitespace-normal", value: (r) => r.reason ?? "", cell: (r) => r.reason },
            { key: "t", header: "Record", value: (r) => r.transaction_number ?? "",
              cell: (r) => <span className="text-caption text-ink-secondary">{r.transaction_number} (corrects {r.corrects})</span> },
          ]} />
      </Card>
    </>
  );
}
