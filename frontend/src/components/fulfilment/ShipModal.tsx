"use client";

/** Create a shipment for reserved stock (courier or sales rep). Shared by stock requests and replenishment requests. */

import { Truck } from "lucide-react";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import type { Reseller } from "@/lib/types";
import { ShippingMethodFields, shippingBody, shippingReady, type Shipping } from "../Shipping";
import { Alert, Button, Field, Input, Modal, ProductCell, Textarea } from "../ui";

export interface ShipLine { key: number; sku: string | null; productName: string | null; reserved: number }

export interface ShipDetails {
  shipping: ReturnType<typeof shippingBody>;
  carrier: string | null;
  tracking_number: string | null;
  shipping_address: string | null;
  notes: string | null;
  quantities: { key: number; quantity: number }[];
}

/** `address` undefined hides the address box (the shipment goes to the shop's own address). */
export function ShipModal({ number, resellerId, lines, address, busy, error, onClose, onSubmit }: {
  number: string; resellerId: number; lines: ShipLine[]; address?: string | null;
  busy: boolean; error: string | null; onClose: () => void; onSubmit: (details: ShipDetails) => void;
}) {
  const [qty, setQty] = useState<Record<number, string>>(() => Object.fromEntries(lines.map((l) => [l.key, String(l.reserved)])));
  const { data: reseller } = useApi<Reseller>(`/resellers/${resellerId}`);
  const [ship, setShip] = useState<Shipping>({ method: "COURIER", carrier: "", repId: "" });
  const shipping = ship.method === "SALES_REP" && ship.repId === "" && reseller?.sales_rep_user_id ? { ...ship, repId: reseller.sales_rep_user_id } : ship;
  const [tracking, setTracking] = useState("");
  const [shipTo, setShipTo] = useState(address ?? "");
  const [notes, setNotes] = useState("");
  const parsed = lines.map((l) => ({ l, q: Number(qty[l.key]) }));
  const invalid = !shippingReady(shipping) || parsed.some(({ l, q }) => !Number.isInteger(q) || q < 0 || q > l.reserved) || parsed.every(({ q }) => !q);
  return (
    <Modal open title={`Ship ${number}`} onClose={onClose}
      description="Moves the reserved stock out of the warehouse to in transit. Only approved, reserved quantities can ship."
      footer={<><Button onClick={onClose}>Back</Button>
        <Button variant="primary" disabled={busy || invalid} onClick={() => onSubmit({
          shipping: shippingBody(shipping), carrier: shipping.method === "COURIER" ? shipping.carrier.trim() : null,
          tracking_number: tracking.trim() || null, shipping_address: shipTo.trim() || null, notes: notes.trim() || null,
          quantities: parsed.map(({ l, q }) => ({ key: l.key, quantity: q })),
        })}><Truck aria-hidden />{busy ? "Shipping…" : "Create shipment"}</Button></>}>
      <Alert>{error}</Alert>
      <ShippingMethodFields value={shipping} onChange={setShip} />
      {shipping.method === "COURIER" && <Field label="Tracking number">{(fid) => <Input id={fid} value={tracking} onChange={(e) => setTracking(e.target.value)} />}</Field>}
      {address !== undefined && <Field label="Shipping address">{(fid) => <Textarea id={fid} rows={2} value={shipTo} onChange={(e) => setShipTo(e.target.value)} />}</Field>}
      <div className="rounded-control border border-line">
        {parsed.map(({ l, q }) => (
          <div key={l.key} className="flex items-center gap-3 border-b border-line px-3 py-2 last:border-0">
            <ProductCell sku={l.sku} name={l.productName} />
            <span className="ml-auto text-caption text-ink-muted">{l.reserved} reserved</span>
            <Input className="w-24" aria-label={`Ship quantity for ${l.sku}`} type="number" min={0} max={l.reserved}
              aria-invalid={q > l.reserved} value={qty[l.key]} onChange={(e) => setQty((s) => ({ ...s, [l.key]: e.target.value }))} />
          </div>
        ))}
      </div>
      <Field label="Shipment notes">{(fid) => <Textarea id={fid} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
    </Modal>
  );
}
