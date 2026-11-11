"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";
import { Alert, Button, Field, Input, Modal, Select, Textarea } from "./ui";

const TYPES = [
  { value: "ISSUE", label: "Issue — something is wrong" },
  { value: "IMPROVEMENT", label: "Improvement — could work better" },
  { value: "QUESTION", label: "Question" },
  { value: "OTHER", label: "Other" },
];

/** Pilot feedback: page, type and description. Role, user and time are recorded by the server. */
export function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const [page, setPage] = useState(() => (typeof document !== "undefined" ? document.title.split(" · ")[0] : "") || pathname);
  const [type, setType] = useState("ISSUE");
  const [description, setDescription] = useState("");
  const [sent, setSent] = useState(false);
  const action = useAction();

  async function submit() {
    const ok = await action.run(() => api.post("/feedback", { page: `${page} (${pathname})`.slice(0, 200), feedback_type: type, description }));
    if (ok) setSent(true);
  }

  return (
    <Modal open title="Pilot feedback" description="Tell us what works, what doesn’t and what is missing." onClose={onClose}
      footer={sent ? <Button variant="primary" onClick={onClose}>Close</Button> : <>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={action.busy || description.trim().length < 3} onClick={submit}>{action.busy ? "Sending…" : "Send feedback"}</Button>
      </>}>
      {sent ? (
        <Alert tone="success" title="Thank you">Your feedback has been recorded for the pilot review.</Alert>
      ) : (
        <>
          <Alert>{action.error}</Alert>
          <Field label="Page / module">{(id) => <Input id={id} value={page} onChange={(e) => setPage(e.target.value)} />}</Field>
          <Field label="Feedback type">{(id) => <Select id={id} value={type} onChange={(e) => setType(e.target.value)} options={TYPES} />}</Field>
          <Field label="Description" required>{(id) => <Textarea id={id} rows={5} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What happened, what you expected, or your suggestion…" />}</Field>
          <p className="text-caption text-ink-muted">Sent as {user?.full_name} ({user?.role_label}) with the date and time.</p>
        </>
      )}
    </Modal>
  );
}
