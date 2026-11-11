"use client";

/** Send an approval to a Relationship Manager (finding 18, D10). Shared by stock and replenishment requests. */

import { useState } from "react";
import type { UserOut } from "@/lib/types";
import { useReference } from "../pickers";
import { Alert, Button, Field, Modal, Select, Textarea } from "../ui";

export function EscalateDialog({ number, busy, error, onClose, onSubmit }: {
  number: string; busy: boolean; error: string | null; onClose: () => void; onSubmit: (body: { to_user_id: number; note: string | null }) => void;
}) {
  const rms = useReference<UserOut[]>("/staff", { role: "RELATIONSHIP_MANAGER" });
  const [to, setTo] = useState<number | "">("");
  const [note, setNote] = useState("");
  return (
    <Modal open title="Send to Relationship Manager" description={`${number} waits for their approval; the warehouse continues once it is approved.`} onClose={onClose}
      footer={<><Button onClick={onClose}>Back</Button>
        <Button variant="primary" disabled={busy || to === ""} onClick={() => onSubmit({ to_user_id: Number(to), note: note.trim() || null })}>
          {busy ? "Sending…" : "Send for approval"}</Button></>}>
      <Alert>{error}</Alert>
      <Field label="Relationship Manager" required>{(id) => <Select id={id} value={to} placeholder={rms ? "Choose…" : "Loading…"} required
        onChange={(e) => setTo(e.target.value ? Number(e.target.value) : "")} options={(rms ?? []).map((u) => ({ value: u.id, label: u.full_name }))} />}</Field>
      <Field label="Note for the approver">{(id) => <Textarea id={id} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Big order from a new dealer" />}</Field>
    </Modal>
  );
}

/** "Waiting for … to approve" banner text. */
export function escalationText(r: { escalated_to?: string | null; escalated_by?: string | null; escalation_note?: string | null }) {
  return `Waiting for ${r.escalated_to ?? "the Relationship Manager"} to approve (sent by ${r.escalated_by ?? "the warehouse"}${r.escalation_note ? `: ${r.escalation_note}` : ""})`;
}
