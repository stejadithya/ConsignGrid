"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";
import type { Balance } from "@/lib/types";
import { ActionMenu, Alert, Button, Field, Input, Modal, Select, Textarea } from "./ui";
import { ShopLabel, TyreLabel } from "./pickers";

type Kind = "block" | "unblock" | "write-off" | "adjust";

/** Row-level stock state actions (all audited, reason required). */
export function StockActions({ row, onDone }: { row: Balance; onDone: () => void }) {
  const { can } = useAuth();
  const [kind, setKind] = useState<Kind | null>(null);
  const [qty, setQty] = useState("1");
  const [direction, setDirection] = useState("-1");
  const [reason, setReason] = useState("");
  const action = useAction();

  const options: { k: Kind; label: string; allowed: boolean }[] = [
    { k: "block", label: "Block", allowed: can("inventory.block") && row.available > 0 },
    { k: "unblock", label: "Unblock", allowed: can("inventory.block") && row.blocked > 0 },
    { k: "write-off", label: "Write off", allowed: can("inventory.adjust") && row.blocked > 0 },
    { k: "adjust", label: "Adjust", allowed: can("inventory.adjust") },
  ];
  const titles: Record<Kind, string> = {
    block: "Block stock (damaged / quarantined)", unblock: "Release blocked stock",
    "write-off": "Write off blocked stock", adjust: "Approved inventory adjustment",
  };

  async function submit() {
    const n = Number(qty);
    const body = { location_id: row.location_id, product_id: row.product_id, reason };
    const ok = await action.run(() =>
      kind === "adjust"
        ? api.post("/inventory/adjustments", { ...body, quantity_delta: n * Number(direction) })
        : api.post(`/inventory/${kind === "write-off" ? "write-offs" : kind}`, { ...body, quantity: n }));
    if (ok) { setKind(null); onDone(); }
  }

  return (
    <>
      <ActionMenu label={`Stock actions for ${row.sku}`} items={options.filter((o) => o.allowed).map((o) => ({
        label: o.label, danger: o.k === "write-off", onSelect: () => { setKind(o.k); setReason(""); setQty("1"); action.setError(null); },
      }))} />
      <Modal open={kind !== null} title={kind ? titles[kind] : ""} onClose={() => setKind(null)}
        footer={<><Button onClick={() => setKind(null)}>Cancel</Button>
          <Button variant={kind === "write-off" || kind === "adjust" ? "danger" : "primary"} disabled={action.busy || reason.trim().length < 3 || Number(qty) <= 0}
            onClick={submit}>{action.busy ? "Saving…" : "Confirm"}</Button></>}>
        <Alert>{action.error}</Alert>
        <p className="text-body text-ink-secondary"><b><TyreLabel sku={row.sku} productId={row.product_id} /></b> at <b><ShopLabel inline code={row.location_code} /></b> — on hand {row.on_hand}, reserved {row.reserved}, blocked {row.blocked}, available {row.available}.</p>
        <div className="grid grid-cols-2 gap-3">
          {kind === "adjust" && (
            <Field label="Direction">{(id) => <Select id={id} value={direction} onChange={(e) => setDirection(e.target.value)}
              options={[{ value: "-1", label: "Decrease (loss)" }, { value: "1", label: "Increase (gain)" }]} />}</Field>
          )}
          <Field label="Quantity" required>{(id) => <Input id={id} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        </div>
        <Field label="Reason" required hint="Recorded on the ledger transaction and audit log.">
          {(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
      </Modal>
    </>
  );
}
