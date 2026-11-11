"use client";

/** "Please call me" about an order (finding 21): the dealer or a sales rep asks the supplier to call. */

import { PhoneCall } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { Alert, Button, Field, Input, Modal } from "../ui";
import { branding } from "@/config/branding";

export function CallMeButton({ requestId, number, size = "sm" }: { requestId: number; number: string; size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [when, setWhen] = useState("");
  const [phone, setPhone] = useState("");
  const action = useAction();
  if (done) return <span className="text-label font-medium text-success">Thanks — {branding.companyName} will call you.</span>;
  return (
    <>
      <Button size={size} onClick={() => setOpen(true)}><PhoneCall aria-hidden />Please call me</Button>
      {open && (
        <Modal open title="Please call me" description={`About order ${number}`} onClose={() => setOpen(false)}
          footer={<><Button onClick={() => setOpen(false)}>Back</Button>
            <Button variant="primary" disabled={action.busy || when.trim().length < 2 || phone.trim().length < 3}
              onClick={async () => { if (await action.run(() => api.post(`/stock-requests/${requestId}/callback`, { preferred_time: when, phone }))) { setOpen(false); setDone(true); } }}>
              {action.busy ? "Sending…" : "Ask for a call"}</Button></>}>
          <Alert>{action.error}</Alert>
          <Field label="When suits you" required>{(id) => <Input id={id} value={when} onChange={(e) => setWhen(e.target.value)} placeholder="e.g. Tomorrow morning" />}</Field>
          <Field label="Phone number" required>{(id) => <Input id={id} type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
        </Modal>
      )}
    </>
  );
}
