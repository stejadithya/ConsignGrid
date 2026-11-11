"use client";

/** How an approval was agreed (finding 17). Shared by stock requests and replenishment requests. */

import { useAuth } from "@/lib/auth";
import { Field, Input, Select, Textarea } from "../ui";

export type ApprovalMethod = "PHONE" | "IN_PERSON" | "EMAIL" | "TEXT" | "STANDARD";
export interface Approval { method: ApprovalMethod | ""; contact: string; comments: string }

export const blankApproval = (): Approval => ({ method: "", contact: "", comments: "" });

export const APPROVAL_METHODS: { value: ApprovalMethod; label: string }[] = [
  { value: "PHONE", label: "Phone call" },
  { value: "IN_PERSON", label: "In person" },
  { value: "EMAIL", label: "Email" },
  { value: "TEXT", label: "Text / WhatsApp" },
  { value: "STANDARD", label: "Standard approval (no contact needed)" },
];

export const approvalLabel = (m: string | null | undefined) => APPROVAL_METHODS.find((x) => x.value === m)?.label ?? m ?? "—";

export function approvalReady(a: Approval) {
  return a.method !== "" && (a.method === "STANDARD" || a.contact.trim().length > 0) && a.comments.trim().length >= 3;
}

export function approvalBody(a: Approval) {
  return { method: a.method, contact: a.method === "STANDARD" ? null : a.contact.trim(), comments: a.comments.trim() };
}

export function ApprovalFields({ value, onChange }: { value: Approval; onChange: (a: Approval) => void }) {
  const { user } = useAuth();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Approved by">{(id) => <Input id={id} readOnly className="bg-subtle" value={user ? `${user.full_name} · ${user.role_label}` : ""} />}</Field>
      <Field label="How was it approved" required>{(id) => <Select id={id} value={value.method} placeholder="Choose…" required
        onChange={(e) => onChange({ ...value, method: e.target.value as ApprovalMethod })} options={APPROVAL_METHODS} />}</Field>
      {value.method !== "STANDARD" && (
        <Field label="Spoke to" required hint="Who agreed it, e.g. the dealer's owner">{(id) => <Input id={id} value={value.contact} required
          onChange={(e) => onChange({ ...value, contact: e.target.value })} />}</Field>
      )}
      <div className="sm:col-span-2">
        <Field label="Comments" required hint="At least 3 characters.">{(id) => <Textarea id={id} rows={2} value={value.comments} required
          onChange={(e) => onChange({ ...value, comments: e.target.value })} />}</Field>
      </div>
    </div>
  );
}
