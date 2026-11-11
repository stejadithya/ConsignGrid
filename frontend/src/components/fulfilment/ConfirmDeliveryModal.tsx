"use client";

/** Confirm what arrived on one shipment, with the receipt proof. Shared by stock requests and replenishment requests. */

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { todayIso } from "@/lib/format";
import type { Delivery } from "@/lib/types";
import { TyreLabel } from "../pickers";
import { blankReceipt, ReceiptFields, receiptBody, receiptReady, type Receipt } from "../ReceiptProof";
import { Alert, Button, Field, Input, Modal } from "../ui";
import { vocab } from "@/lib/terms";

export interface DeliveryConfirmation extends ReturnType<typeof receiptBody> {
  delivered_on: string;
  reference: string | null;
  lines: { line_id: number; qty_received: number }[];
}

export function ConfirmDeliveryModal({ d, busy, error, onClose, onSubmit }: {
  d: Delivery; busy: boolean; error: string | null; onClose: () => void; onSubmit: (body: DeliveryConfirmation) => void;
}) {
  const { user } = useAuth();
  const [qty, setQty] = useState<Record<number, string>>(() => Object.fromEntries(d.lines.map((l) => [l.id, String(l.qty_dispatched)])));
  const [date, setDate] = useState(todayIso());
  const [reference, setReference] = useState("");
  const [receipt, setReceipt] = useState<Receipt>(blankReceipt);
  const invalid = d.lines.some((l) => { const q = Number(qty[l.id]); return !Number.isInteger(q) || q < 0 || q > l.qty_dispatched; }) || !date
    || !receiptReady(receipt, user);
  const short = d.lines.some((l) => Number(qty[l.id]) < l.qty_dispatched);
  return (
    <Modal open title={`Confirm delivery of ${d.number}`} onClose={onClose}
      description={`Record what actually arrived. Received stock moves into the ${vocab.partner}'s consignment stock.`}
      footer={<><Button onClick={onClose}>Back</Button>
        <Button variant="primary" disabled={busy || invalid} onClick={() => onSubmit({
          delivered_on: date, reference: reference.trim() || null, ...receiptBody(receipt),
          lines: d.lines.map((l) => ({ line_id: l.id, qty_received: Number(qty[l.id]) })),
        })}>{busy ? "Saving…" : "Confirm delivery"}</Button></>}>
      <Alert>{error}</Alert>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Delivery date" required>{(fid) => <Input id={fid} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
        <Field label="Delivery reference" hint="Proof-of-delivery or docket number">{(fid) => <Input id={fid} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
      </div>
      <div className="rounded-control border border-line">
        {d.lines.map((l) => (
          <div key={l.id} className="flex items-center gap-3 border-b border-line px-3 py-2 last:border-0">
            <TyreLabel sku={l.sku} productId={l.product_id} />
            <span className="ml-auto text-caption text-ink-muted">{l.qty_dispatched} shipped</span>
            <Input className="w-24" aria-label={`Received quantity for ${l.sku}`} type="number" min={0} max={l.qty_dispatched}
              value={qty[l.id]} onChange={(e) => setQty((s) => ({ ...s, [l.id]: e.target.value }))} />
          </div>
        ))}
      </div>
      {short && <Alert tone="warn">Short quantities stay in transit until the warehouse resolves them (returned, lost or late delivery).</Alert>}
      <ReceiptFields value={receipt} onChange={setReceipt} user={user} />
    </Modal>
  );
}
