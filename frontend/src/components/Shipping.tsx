"use client";

import { FileText, Mail } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Delivery, Transfer, UserOut } from "@/lib/types";
import { useReference } from "./pickers";
import { Button, Field, Input, Select } from "./ui";

export interface Shipping { method: "COURIER" | "SALES_REP"; carrier: string; repId: number | "" }

export const shippingBody = (s: Shipping) => s.method === "SALES_REP"
  ? { shipping_method: "SALES_REP", carried_by_user_id: s.repId || null }
  : { shipping_method: "COURIER" };

export const shippingReady = (s: Shipping, carrierRequired = true) =>
  s.method === "SALES_REP" ? s.repId !== "" : !carrierRequired || s.carrier.trim() !== "";

/** Courier (carrier name) or a sales representative who carries the tyres to the reseller. */
export function ShippingMethodFields({ value, onChange, carrierLabel = "Carrier", carrierRequired = true }: {
  value: Shipping; onChange: (s: Shipping) => void; carrierLabel?: string; carrierRequired?: boolean;
}) {
  const loaded = useReference<UserOut[]>("/staff", { role: "SALES_REP" });
  const reps = loaded ?? [];
  return (
    <div className="space-y-3">
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1.5 text-label font-medium text-ink">Send with</legend>
        {([["COURIER", "Courier"], ["SALES_REP", "Sales representative"]] as const).map(([v, label]) => (
          <label key={v} className={`flex cursor-pointer items-center gap-2 rounded-control border px-3 py-2 text-body ${value.method === v ? "border-ink bg-subtle font-medium" : "border-line"}`}>
            <input type="radio" name="shipping-method" className="size-4 accent-ink" checked={value.method === v} onChange={() => onChange({ ...value, method: v })} />{label}
          </label>
        ))}
      </fieldset>
      {value.method === "COURIER"
        ? <Field label={carrierLabel} required={carrierRequired}>{(id) => <Input id={id} value={value.carrier} onChange={(e) => onChange({ ...value, carrier: e.target.value })} placeholder="e.g. StarTrack" />}</Field>
        : <Field label="Sales representative" required hint="They are notified and confirm the delivery when they hand the tyres over.">
            {(id) => <Select id={id} value={value.repId} onChange={(e) => onChange({ ...value, repId: e.target.value ? Number(e.target.value) : "" })}
              placeholder={loaded ? "Select sales representative…" : "Loading…"} options={reps.map((u) => ({ value: u.id, label: u.full_name }))} />}
          </Field>}
    </div>
  );
}

/** Download the delivery note PDF; staff can (re)send it to the reseller by email. */
export function DeliveryNoteActions({ delivery, onChanged }: { delivery: Delivery; onChanged?: () => void }) {
  const { can, user } = useAuth();
  return <NoteActions received={!!delivery.received_at} pdfUrl={`/api/replenishment/deliveries/${delivery.id}/delivery-note.pdf`}
    emailPath={`/replenishment/deliveries/${delivery.id}/email-delivery-note`} canEmail={!user?.reseller_id && can("replenishment.manage")}
    emailedAt={delivery.note_emailed_at} emailTo={delivery.note_email_to} emailError={delivery.note_email_error} onChanged={onChanged} />;
}

/** The same actions for a transfer between dealers (finding 23): PDF for staff and the receiving dealer. */
export function TransferNoteActions({ transfer, onChanged }: { transfer: Transfer; onChanged?: () => void }) {
  const { can, user } = useAuth();
  if (user?.reseller_id && user.reseller_id !== transfer.destination_reseller_id) return null;
  return <NoteActions received={!!transfer.received_at} pdfUrl={`/api/transfers/${transfer.id}/delivery-note.pdf`}
    emailPath={`/transfers/${transfer.id}/email-delivery-note`} canEmail={!user?.reseller_id && can("transfer.approve")}
    emailedAt={transfer.note_emailed_at} emailTo={transfer.note_email_to} emailError={transfer.note_email_error} onChanged={onChanged} />;
}

function NoteActions({ received, pdfUrl, emailPath, canEmail, emailedAt, emailTo, emailError, onChanged }: {
  received: boolean; pdfUrl: string; emailPath: string; canEmail: boolean; emailedAt?: string | null; emailTo?: string | null;
  emailError?: string | null; onChanged?: () => void;
}) {
  const action = useAction();
  if (!received) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-caption">
      <a className="inline-flex items-center gap-1 font-medium text-ink underline decoration-brand decoration-2 underline-offset-4"
        href={pdfUrl} target="_blank" rel="noreferrer">
        <FileText className="size-3.5" aria-hidden />Delivery note (PDF)
      </a>
      {canEmail && <Button size="sm" variant="ghost" disabled={action.busy}
        onClick={async () => { if (await action.run(() => api.post(emailPath))) onChanged?.(); }}>
        <Mail aria-hidden />{emailedAt ? "Resend email" : "Email to dealer"}</Button>}
      <span className="text-ink-muted">
        {emailedAt ? `Emailed to ${emailTo} on ${fmtDateTime(emailedAt)}` : emailError ?? ""}
      </span>
      {action.error && <span className="text-danger">{action.error}</span>}
    </div>
  );
}
