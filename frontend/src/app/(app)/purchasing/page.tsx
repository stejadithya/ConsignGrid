"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { LocationSelect, ProductSelect, useLocations, TyreLabel } from "@/components/pickers";
import { Alert, Badge, Button, Card, DataTable, Field, Input, Modal, PageHeader, Tabs, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { GoodsReceipt, Proposal, PurchaseOrder } from "@/lib/types";

export default function PurchasingPage() {
  const { can } = useAuth();
  const params = useSearchParams();   // opened from "Incoming": search the orders for that tyre
  const [tab, setTab] = useState(params.get("tab") === "receipts" ? "receipts" : "orders");
  const { data: pos, error, reload } = useApi<PurchaseOrder[]>("/purchasing/purchase-orders");
  const { data: receipts, reload: reloadReceipts } = useApi<GoodsReceipt[]>("/purchasing/receipts");
  const [creating, setCreating] = useState(false);
  const [receiving, setReceiving] = useState<PurchaseOrder | "adhoc" | null>(null);
  const [msg, setMsg] = useState<GoodsReceipt | null>(null);
  return (
    <>
      <PageHeader title="Purchasing & shipments" subtitle="Incoming supplier stock. An expected shipment is not stock until it is received, and a receipt never closes a backorder by itself."
        actions={<>
          {can("inventory.receive") && <Button onClick={() => setReceiving("adhoc")}>Receive without PO</Button>}
          {can("purchasing.manage") && <Button variant="primary" onClick={() => setCreating(true)}>New purchase order</Button>}
        </>} />
      <Alert>{error}</Alert>
      {msg && <Alert tone="success">Received {msg.number}: {msg.lines.reduce((a, l) => a + l.qty_received, 0)} unit(s).{" "}
        {msg.open_backorders_for_received_skus > 0 ? <><b>{msg.open_backorders_for_received_skus}</b> open backorder(s) are waiting for these SKUs — <Link className="underline" href="/backorders">review the allocation proposal</Link>.</> : "No open backorders for these SKUs."}</Alert>}
      {msg && msg.open_backorders_for_received_skus > 0 && can("replenishment.manage") && <FillBackorders key={msg.id} receipt={msg} />}
      <Tabs active={tab} onChange={setTab} tabs={[{ id: "orders", label: "Purchase orders" }, { id: "receipts", label: "Goods receipts" }]} />
      {tab === "orders" && (
        <Card padded={false}>
          <DataTable mobile="cards" label="Purchase orders" rows={pos} rowKey={(p) => p.id} initialSearch={params.get("q") ?? ""} empty="No purchase orders yet" emptyHint="Create a purchase order to track stock expected from suppliers. Incoming stock is never counted as on hand." columns={[
            { key: "n", mobile: "primary", header: "PO", value: (p) => p.number, cell: (p) => <span className="font-medium">{p.number}</span> },
            { key: "s", mobile: "secondary", header: "Supplier", value: (p) => p.supplier_name, cell: (p) => <>{p.supplier_name}<div className="text-caption text-ink-muted">{p.supplier_reference}</div></> },
            { key: "e", mobile: "field", mobileOrder: 1, header: "Expected", value: (p) => p.expected_date, cell: (p) => fmtDate(p.expected_date) },
            { key: "l", mobile: "field", mobileLabel: "Received / ordered", mobileOrder: 2, header: "Lines (received / ordered)", value: (p) => p.lines.map((l) => l.sku).join(" "), className: "min-w-56 whitespace-normal", cell: (p) => <ul className="text-caption">{p.lines.map((l) => <li key={l.id}><TyreLabel sku={l.sku} productId={l.product_id} />: <span className="num">{l.qty_received}/{l.qty_ordered}</span></li>)}</ul> },
            { key: "st", mobile: "status", header: "Status", value: (p) => p.status, cell: (p) => <Badge value={p.status} /> },
            { key: "a", mobile: "action", header: "", cell: (p) => ["OPEN", "PARTIALLY_RECEIVED"].includes(p.status) && can("inventory.receive") && <Button size="sm" onClick={() => setReceiving(p)}>Receive</Button> },
          ]} />
        </Card>
      )}
      {tab === "receipts" && (
        <Card padded={false}>
          <DataTable mobile="cards" label="Receipts" rows={receipts} rowKey={(r) => r.id} initialSearch={tab === "receipts" ? params.get("q") ?? "" : ""} empty="No goods received yet" emptyHint="Receive supplier stock (with or without a purchase order) to start warehouse inventory." columns={[
            { key: "n", mobile: "primary", header: "Receipt", value: (r) => r.number, cell: (r) => r.number },
            { key: "d", mobile: "field", mobileOrder: 1, header: "Received", value: (r) => r.received_at, cell: (r) => <>{fmtDateTime(r.received_at)}<div className="text-caption text-ink-muted">{r.received_by}</div></> },
            { key: "ref", mobile: "field", mobileOrder: 2, header: "Supplier ref.", cell: (r) => r.supplier_reference ?? "—" },
            { key: "l", mobile: "field", mobileOrder: 3, header: "Lines", className: "min-w-56 whitespace-normal", cell: (r) => <ul className="text-caption">{r.lines.map((l) => <li key={l.id}><TyreLabel sku={l.sku} productId={l.product_id} /> <span className="num">×{l.qty_received}</span>{l.qty_damaged > 0 && <span className="text-danger"> ({l.qty_damaged} damaged → blocked)</span>}</li>)}</ul> },
          ]} />
        </Card>
      )}
      {creating && <NewPO onClose={() => setCreating(false)} onDone={() => { setCreating(false); reload(); }} />}
      {receiving && <Receive po={receiving === "adhoc" ? null : receiving} onClose={() => setReceiving(null)} onDone={(r) => { setReceiving(null); setMsg(r); reload(); reloadReceipts(); }} />}
    </>
  );
}

function NewPO({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const warehouses = useLocations(["WAREHOUSE"]);
  const [wh, setWh] = useState<number | "">("");
  const [supplier, setSupplier] = useState("");
  const [ref, setRef] = useState("");
  const [expected, setExpected] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<{ product: number | ""; qty: string; cost: string }[]>([{ product: "", qty: "", cost: "" }]);
  const action = useAction();
  const whId = wh || warehouses?.find((w) => w.is_default_warehouse)?.id || "";
  return (
    <Modal open wide title="New purchase order" onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={action.busy || !supplier || !whId}
        onClick={async () => { if (await action.run(() => api.post("/purchasing/purchase-orders", { supplier_name: supplier, supplier_reference: ref || null, warehouse_location_id: whId, expected_date: expected || null, notes: notes || null,
          lines: lines.filter((l) => l.product && Number(l.qty) > 0).map((l) => ({ product_id: l.product, qty_ordered: Number(l.qty), unit_cost: l.cost || null })) }))) onDone(); }}>Create PO</Button></>}>
      <Alert>{action.error}</Alert>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Supplier" required>{(id) => <Input id={id} value={supplier} onChange={(e) => setSupplier(e.target.value)} />}</Field>
        <Field label="Supplier reference">{(id) => <Input id={id} value={ref} onChange={(e) => setRef(e.target.value)} />}</Field>
        <Field label="Receiving warehouse">{(id) => <LocationSelect id={id} types={["WAREHOUSE"]} value={whId} onChange={setWh} />}</Field>
        <Field label="Expected date">{(id) => <Input id={id} type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />}</Field>
      </div>
      {lines.map((l, i) => (
        <div key={i} className="grid grid-cols-[1fr_80px_100px] gap-2">
          <ProductSelect value={l.product} onChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, product: v } : x)))} />
          <Input type="number" min={1} placeholder="Qty" aria-label="Quantity" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} />
          <Input type="number" min={0} step="0.01" placeholder="Unit cost" aria-label="Unit cost" value={l.cost} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, cost: e.target.value } : x)))} />
        </div>
      ))}
      <Button size="sm" onClick={() => setLines((ls) => [...ls, { product: "", qty: "", cost: "" }])}>Add line</Button>
      <Field label="Notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
    </Modal>
  );
}

function Receive({ po, onClose, onDone }: { po: PurchaseOrder | null; onClose: () => void; onDone: (r: GoodsReceipt) => void }) {
  const warehouses = useLocations(["WAREHOUSE"]);
  const [ref, setRef] = useState("");
  const [lines, setLines] = useState<{ po_line?: number; product: number | ""; sku?: string | null; max?: number; qty: string; damaged: string }[]>(
    po ? po.lines.filter((l) => l.qty_outstanding > 0).map((l) => ({ po_line: l.id, product: l.product_id, sku: l.sku, max: l.qty_outstanding, qty: String(l.qty_outstanding), damaged: "0" }))
      : [{ product: "", qty: "", damaged: "0" }]);
  const action = useAction();
  const whId = po?.warehouse_location_id ?? warehouses?.find((w) => w.is_default_warehouse)?.id;
  return (
    <Modal open wide title={po ? `Receive against ${po.number}` : "Receive goods (no purchase order)"} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={action.busy || !whId}
        onClick={async () => { const r = await action.run(() => api.post<GoodsReceipt>("/purchasing/receipts", { warehouse_location_id: whId, purchase_order_id: po?.id ?? null, supplier_reference: ref || null,
          lines: lines.filter((l) => l.product && Number(l.qty) > 0).map((l) => ({ product_id: l.product, purchase_order_line_id: l.po_line ?? null, qty_received: Number(l.qty), qty_damaged: Number(l.damaged || 0) })) })); if (r) onDone(r); }}>Post receipt</Button></>}>
      <Alert>{action.error}</Alert>
      <p className="text-body text-ink-secondary">Received stock becomes available in the warehouse. Damaged units are received as blocked. Allocation to backorders is proposed separately for confirmation.</p>
      <Field label="Supplier delivery reference">{(id) => <Input id={id} value={ref} onChange={(e) => setRef(e.target.value)} />}</Field>
      <div className="grid grid-cols-[1fr_90px_90px] gap-2 text-caption font-medium text-ink-secondary"><span>Product</span><span>Received</span><span>Damaged</span></div>
      {lines.map((l, i) => (
        <div key={i} className="grid grid-cols-[1fr_90px_90px] items-center gap-2">
          {l.po_line ? <span className="text-body"><TyreLabel sku={l.sku} productId={l.product || null} /> <span className="text-caption text-ink-muted">(outstanding {l.max})</span></span>
            : <ProductSelect value={l.product} onChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, product: v } : x)))} />}
          <Input type="number" min={0} max={l.max} aria-label="Received" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} />
          <Input type="number" min={0} aria-label="Damaged" value={l.damaged} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, damaged: e.target.value } : x)))} />
        </div>
      ))}
      {!po && <Button size="sm" onClick={() => setLines((ls) => [...ls, { product: "", qty: "", damaged: "0" }])}>Add line</Button>}
    </Modal>
  );
}

/** Straight after a receipt: the backorders the received tyres can fill now, and one click to reserve them (the same
 *  confirmation as Backorders → Proposed allocation; nothing is reserved until it is pressed). */
function FillBackorders({ receipt }: { receipt: GoodsReceipt }) {
  const received = new Set(receipt.lines.map((l) => l.product_id));
  const { data, error } = useApi<Proposal[]>("/replenishment/allocation-proposal", { warehouse_location_id: receipt.warehouse_location_id });
  const rows = (data ?? []).filter((p) => received.has(p.product_id) && p.proposed_qty > 0);
  const [done, setDone] = useState<string | null>(null);
  const action = useAction();
  async function fill() {
    const r = await action.run(() => api.post("/replenishment/allocation-proposal/confirm", {
      warehouse_location_id: receipt.warehouse_location_id, lines: rows.map((p) => ({ request_id: p.request_id, quantity: p.proposed_qty })) }));
    if (r) setDone(`Reserved stock for ${rows.length} backorder(s). Dispatch them from Replenishment → Pick & dispatch.`);
  }
  if (done) return <Alert tone="success">{done} <Link className="underline" href="/replenishment">Go to Pick &amp; dispatch</Link></Alert>;
  if (!data || rows.length === 0) return <Alert>{error}</Alert>;
  return (
    <Card title={`${rows.length} backorder(s) can be filled now`} subtitle="Highest priority first, then oldest. Nothing is reserved until you confirm." className="mb-4"
      actions={<><Link className="link text-label" href="/backorders">Review first</Link>
        <Button size="sm" variant="primary" disabled={action.busy} onClick={fill}>Fill {rows.length} backorder(s)</Button></>}>
      <Alert>{action.error ?? error}</Alert>
      <ul className="divide-y divide-line text-body">
        {rows.map((p) => (
          <li key={p.request_id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
            <span><Link className="link" href={`/replenishment/${p.request_id}`}>{p.request_number}</Link> · {p.reseller_name} <span className="text-ink-secondary">({p.location_code})</span></span>
            <span className="text-ink-secondary"><TyreLabel sku={p.sku} productId={p.product_id} /> · <b className="num text-ink">{p.proposed_qty}</b> of {p.awaiting_supply}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
