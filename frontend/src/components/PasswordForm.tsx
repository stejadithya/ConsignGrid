"use client";

import { CircleCheck, Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";
import type { Me } from "@/lib/types";
import { Alert, Button, Field, Input } from "./ui";

const MIN = 10;
const MAX_BYTES = 72;   // the server's limit: bytes, so accented letters and emoji count double or more
const bytes = (v: string) => new TextEncoder().encode(v).length;

/** A password box with a show / hide toggle. */
function SecretInput({ id, value, onChange, autoComplete, invalid }: {
  id: string; value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={shown ? "text" : "password"} autoComplete={autoComplete} required aria-invalid={invalid}
        className="h-10 w-full pr-11" value={value} onChange={(e) => onChange(e.target.value)} />
      {/* A toggle: the name stays "Show password" and aria-pressed says whether it is on. 44px tap area on touch. */}
      <button type="button" onClick={() => setShown((s) => !s)} aria-label="Show password" aria-pressed={shown} title={shown ? "Hide password" : "Show password"}
        className="touch-target absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-ink-secondary hover:text-ink focus-visible:outline-2 focus-visible:outline-ink">
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
      </button>
    </div>
  );
}

/** Change the signed-in user's own password. With onDone, a success screen offers Close (which calls onDone). */
export function PasswordForm({ onDone }: { onDone?: () => void }) {
  const { setUser } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const action = useAction();
  const mismatch = confirm.length > 0 && confirm !== next;
  const short = next.length > 0 && next.length < MIN;
  const long = bytes(next) > MAX_BYTES;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next.length < MIN || long || next !== confirm) return;
    const me = await action.run(() => api.post<Me>("/auth/password", { current_password: current, new_password: next }));
    if (me) {
      setDone(true);
      setUser(me);
    }
  }

  if (done && onDone) {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <CircleCheck className="size-10 text-success" aria-hidden />
        <div className="text-subheading font-semibold text-ink">Password changed</div>
        <p className="text-body text-ink-secondary">Use your new password the next time you sign in.</p>
        <Button variant="primary" className="mt-2 w-full" onClick={onDone}>Close</Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <p className="rounded-control bg-subtle px-3.5 py-2.5 text-label text-ink-secondary">Your new password needs <b className="font-medium text-ink">at least {MIN} characters</b>. Any letters, numbers, spaces or symbols are fine. It can&apos;t be your current password or one of the two before it.</p>
      <Alert>{action.error}</Alert>
      <Alert tone="success">{done ? "Password changed." : null}</Alert>
      <Field label="Current password">{(id) => <SecretInput id={id} autoComplete="current-password" value={current} onChange={setCurrent} />}</Field>
      <Field label="New password" error={short ? `At least ${MIN} characters (${next.length} so far).`
        : long ? "Too long: use 72 characters or fewer (fewer with accented letters or emoji)." : undefined}>
        {(id) => <SecretInput id={id} autoComplete="new-password" value={next} onChange={setNext} invalid={short || long} />}
      </Field>
      <Field label="Confirm new password" hint="Type the new password again." error={mismatch ? "The passwords do not match." : undefined}>
        {(id) => <SecretInput id={id} autoComplete="new-password" value={confirm} onChange={setConfirm} invalid={mismatch} />}
      </Field>
      <Button type="submit" variant="primary" className="w-full" disabled={action.busy || next.length < MIN || long || next !== confirm || !current}>
        {action.busy ? "Saving…" : "Save new password"}
      </Button>
    </form>
  );
}
