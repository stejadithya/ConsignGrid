"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Delivery, DeliveryLine } from "@/lib/types";
import { Alert, Badge, Button, ConfirmDialog, DataTable, Field, Input, Modal, Select } from "./ui";
import { ShopLabel, TyreLabel } from "./pickers";
import { blankReceipt, canConfirmCarried, ReceiptFields, receiptBody, receiptReady, ReceiptView, type Receipt } from "./ReceiptProof";
import { DeliveryNoteActions } from "./Shipping";
import { vocab } from "@/lib/terms";

/** Receive a delivery (with optional short quantities) and resolve discrepancies. */
export function DeliveryActions({ delivery, onChanged }: { delivery: Delivery; onChanged: () => void }) {
  const { can, user } = useAuth();
  const [receiving, setReceiving] = useState(false);
  const [receipt, setReceipt] = useState<Receipt>(blankReceipt);
  // Carried by a Sales Rep: only the dealer or that Sales Rep confirms.
  const mayConfirm = can("delivery.confirm") && canConfirmCarried(user, delivery.shipping_method === "SALES_REP" ? delivery.carried_by_user_id : null);
  const [qty, setQty] = useState<Record<number, string>>({});
  const [resolve, setResolve] = useState<DeliveryLine | null>(null);
  const [outcome, setOutcome] = useState("RETURN_TO_WAREHOUSE");
  const [rq, setRq] = useState("1");
  const action = useAction();

  async function receive() {
    const ok = await action.run(() => api.post(`/replenishment/deliveries/${delivery.id}/receive`, {
      lines: delivery.lines.map((l) => ({ line_id: l.id, qty_received: Number(qty[l.id] ?? l.qty_dispatched) })),
      ...receiptBody(receipt),
    }));
    if (ok) { setReceiving(false); onChanged(); }
  }

  return (
    <div className="flex flex-wrap gap-1">
      <DeliveryNoteActions delivery={delivery} onChanged={onChanged} />
      {delivery.status === "IN_TRANSIT" && mayConfirm && <Button size="sm" variant="primary" onClick={() => { setReceiving(true); setQty({}); setReceipt(blankReceipt()); action.setError(null); }}>Confirm receipt</Button>}
      {delivery.status === "IN_TRANSIT" && !mayConfirm && can("delivery.confirm") && delivery.carried_by &&
        <span className="text-caption text-ink-muted">To be confirmed by the {vocab.partner} or {delivery.carried_by}</span>}
      {delivery.status === "RECEIVED_WITH_DISCREPANCY" && can("replenishment.manage") && delivery.lines.filter((l) => l.qty_open > 0).map((l) => (
        <Button key={l.id} size="sm" variant="danger" onClick={() => { setResolve(l); setRq(String(l.qty_open)); action.setError(null); }}>Resolve {l.sku} ({l.qty_open})</Button>
      ))}
      <Modal open={receiving} wide title={`Confirm receipt of ${delivery.number}`} onClose={() => setReceiving(false)}
        footer={<><Button onClick={() => setReceiving(false)}>Cancel</Button><Button variant="primary" disabled={action.busy || !receiptReady(receipt, user)} onClick={receive}>{action.busy ? "Saving…" : "Confirm receipt"}</Button></>}>
        <Alert>{action.error}</Alert>
        <p className="text-body text-ink-secondary">Delivered to <b>{delivery.reseller_name}</b> (<ShopLabel inline code={delivery.to_location_code} withDealer={false} />). Enter what actually arrived; any shortfall stays visible in transit until resolved.</p>
        <DataTable mobile="cards" density="comfortable" label={`${vocab.Items} received`} search={false} rows={delivery.lines} rowKey={(l) => l.id} columns={[
          { key: "s", mobile: "primary", header: vocab.Item, className: "min-w-48 whitespace-normal", cell: (l) => <TyreLabel sku={l.sku} productId={l.product_id} /> },
          { key: "r", mobile: "secondary", header: "Request", cell: (l) => l.request_number },
          { key: "d", mobile: "field", mobileOrder: 1, header: "Dispatched", align: "right", cell: (l) => l.qty_dispatched },
          { key: "q", mobile: "field", mobileOrder: 2, header: "Received", cell: (l) => <Input className="w-20" type="number" min={0} max={l.qty_dispatched} aria-label={`Received ${l.sku}`} value={qty[l.id] ?? String(l.qty_dispatched)} onChange={(e) => setQty((x) => ({ ...x, [l.id]: e.target.value }))} /> },
        ]} />
        <ReceiptFields value={receipt} onChange={setReceipt} user={user} />
      </Modal>
      <ConfirmDialog open={!!resolve} title={`Resolve discrepancy — ${resolve?.sku}`} requireReason danger={outcome === "LOST"} busy={action.busy} error={action.error}
        onClose={() => setResolve(null)}
        onConfirm={async (reason) => { if (await action.run(() => api.post(`/replenishment/deliveries/${delivery.id}/resolve`, { line_id: resolve!.id, outcome, quantity: Number(rq), reason }))) { setResolve(null); onChanged(); } }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Outcome">{(id) => <Select id={id} value={outcome} onChange={(e) => setOutcome(e.target.value)} options={[
            { value: "RETURN_TO_WAREHOUSE", label: "Returned to warehouse" }, { value: "LATE_DELIVERY", label: `Arrived late at ${vocab.partner}` },
            { value: "LOST", label: "Lost / write off (needs adjust permission)" }]} />}</Field>
          <Field label={`Quantity (max ${resolve?.qty_open})`}>{(id) => <Input id={id} type="number" min={1} value={rq} onChange={(e) => setRq(e.target.value)} />}</Field>
        </div>
        <p className="text-caption text-ink-secondary">Returned and lost quantities go back to &ldquo;awaiting supply&rdquo; on the request; late deliveries count as delivered.</p>
      </ConfirmDialog>
    </div>
  );
}

export function DeliveriesTable({ rows, onChanged, initialSearch }: { rows: Delivery[] | null; onChanged: () => void; initialSearch?: string }) {
  return (
    <DataTable mobile="cards" label="Deliveries" rows={rows} rowKey={(d) => d.id} initialSearch={initialSearch} columns={[
      { key: "n", mobile: "primary", header: "Delivery", value: (d) => d.number, cell: (d) => <span className="font-medium">{d.number}</span> },
      { key: "to", mobile: "secondary", header: "To", value: (d) => d.to_location_code, cell: (d) => <ShopLabel code={d.to_location_code} dealer={d.reseller_name} /> },
      { key: "l", header: "Lines", cell: (d) => <ul className="text-caption">{d.lines.map((l) => <li key={l.id}>{l.sku} ×{l.qty_dispatched}{l.qty_received > 0 && ` · recv ${l.qty_received}`}{l.qty_open > 0 && d.status !== "IN_TRANSIT" && <b className="text-danger"> · {l.qty_open} unresolved</b>}</li>)}</ul> },
      { key: "d", mobile: "field", mobileOrder: 1, header: "Dispatched", value: (d) => d.dispatched_at, cell: (d) => <span className="text-caption">{fmtDateTime(d.dispatched_at)}<br />{d.dispatched_by}{d.carrier_reference && ` · ${d.carrier_reference}`}</span> },
      { key: "r", mobile: "field", mobileOrder: 2, header: "Received", className: "whitespace-normal", cell: (d) => d.received_at
        ? <div className="min-w-40 text-caption">{fmtDateTime(d.received_at)}<br />{d.received_by}
            <div className="mt-1"><ReceiptView receivedBy={d.received_by_name} notes={d.receipt_notes} photos={d.photos} retired={d.photos_retired} /></div></div>
        : <span className="text-caption">—</span> },
      { key: "s", mobile: "status", header: "Status", value: (d) => d.status, cell: (d) => <Badge value={d.status} /> },
      { key: "a", mobile: "action", header: "", cell: (d) => <DeliveryActions delivery={d} onChanged={onChanged} /> },
    ]} />
  );
}
