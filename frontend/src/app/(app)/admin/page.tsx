"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { invalidateReference, ResellerSelect, useResellers } from "@/components/pickers";
import {
  Alert, Badge, Button, Card, ConfirmDialog, DataTable, Field, FilterField, Input, Modal, PageHeader, Select, Tabs, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { ROLE_LABELS } from "@/config/roles";
import type { AuditEvent, Location, PartnerKey, Reconciliation, RoleCode, TaxRate, UserOut } from "@/lib/types";

const ALL_ROLES = Object.keys(ROLE_LABELS) as RoleCode[];

export default function AdminPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState(can("user.manage") ? "users" : "audit");
  return (
    <>
      <PageHeader title="Administration" subtitle="Pilot users, tax rates, warehouses, pilot feedback, audit log and ledger reconciliation." />
      <Tabs active={tab} onChange={setTab} tabs={[
        ...(can("user.manage") ? [{ id: "users", label: "Users" }] : []),
        { id: "tax", label: "Tax rates" }, { id: "warehouses", label: "Warehouses" },
        ...(can("audit.read") ? [{ id: "feedback", label: "Pilot feedback" }] : []),
        { id: "audit", label: "Audit log" }, { id: "reconcile", label: "Reconciliation" },
        ...(can("partner_keys.manage") ? [{ id: "website", label: "Website access" }] : []),
      ]} />
      {tab === "feedback" && <Feedback />}
      {tab === "users" && <Users />}
      {tab === "tax" && <TaxRates />}
      {tab === "warehouses" && <Warehouses />}
      {tab === "audit" && <Audit />}
      {tab === "reconcile" && <Reconcile />}
      {tab === "website" && <WebsiteAccess />}
    </>
  );
}

/** Locked after too many wrong passwords (the lock ends by itself after 15 minutes). */
const locked = (u: Partial<UserOut>) => !!u.locked_until && new Date(u.locked_until).getTime() > Date.now();

function Users() {
  const { user: me } = useAuth();
  const initialQ = useSearchParams()?.get("q") ?? "";   // ?q= from the search box: that person
  // Only an Administrator may create or assign the Administrator role (also enforced by the API).
  const ROLES = me?.role === "ADMINISTRATOR" ? ALL_ROLES : ALL_ROLES.filter((r) => r !== "ADMINISTRATOR");
  const { data, error, reload } = useApi<UserOut[]>("/users");
  const resellers = useResellers();
  const [edit, setEdit] = useState<Partial<UserOut> & { password?: string } | null>(null);
  // New user form: "Is this person replacing someone?" (finding 32).
  const [replaces, setReplaces] = useState<{ on: boolean; user: number | ""; mode: "TAKE_OVER" | "SHARE"; dealers: number[] }>(
    { on: false, user: "", mode: "TAKE_OVER", dealers: [] });
  const colleagues = (data ?? []).filter((u) => u.is_active && !u.reseller_id && u.role === edit?.role && u.id !== edit?.id);
  const dealersOf = (uid: number | "") => (resellers ?? []).filter((r) => uid !== "" && r.sales_rep_user_id === uid);
  const [handover, setHandover] = useState<UserOut | null>(null);
  const action = useAction();
  const resellerName = (id: number | null) => resellers?.find((r) => r.id === id)?.business_name ?? "—";
  const unlock = async (u: UserOut) => { if (await action.run(() => api.post(`/users/${u.id}/unlock`, {}))) { setEdit(null); reload(); } };
  async function save() {
    if (!edit) return;
    const body = { full_name: edit.full_name, phone: (edit.phone ?? "").trim() || null, role: edit.role, reseller_id: edit.role === "RESELLER" ? edit.reseller_id : null,
      ...(edit.password ? { password: edit.password } : {}) };
    const ok = await action.run(() => edit.id
      ? api.patch(`/users/${edit.id}`, { ...body, is_active: edit.is_active })
      : api.post("/users", { ...body, email: edit.email, password: edit.password,
          ...(replaces.on && replaces.user !== "" ? { replaces: { user_id: replaces.user, mode: replaces.mode,
            reseller_ids: replaces.mode === "SHARE" ? replaces.dealers : null } } : {}) }));
    if (ok) { setEdit(null); reload(); invalidateReference(); }
  }
  return (
    <Card padded={false} actions={<Button size="sm" variant="primary" onClick={() => { action.setError(null); setReplaces({ on: false, user: "", mode: "TAKE_OVER", dealers: [] }); setEdit({ role: "SALES_REP", is_active: true }); }}>New user</Button>} title="Users">
      <Alert>{error}</Alert>
      <DataTable mobile="cards" label="Users" rows={data} rowKey={(u) => u.id} initialSearch={initialQ} onRowClick={(u) => { action.setError(null); setEdit({ ...u }); }} columns={[
        { key: "n", mobile: "primary", header: "Name", value: (u) => u.full_name, cell: (u) => u.full_name },
        { key: "e", mobile: "field", mobileOrder: 1, header: "Email", value: (u) => u.email, cell: (u) => u.email },
        { key: "p", header: "Phone", value: (u) => u.phone ?? "", cell: (u) => u.phone ?? "—" },
        { key: "r", mobile: "secondary", header: "Role", value: (u) => u.role, cell: (u) => ROLE_LABELS[u.role as RoleCode] ?? humanize(u.role) },
        { key: "rs", mobile: "field", mobileOrder: 2, header: "Dealer", cell: (u) => (u.reseller_id ? resellerName(u.reseller_id)
          : u.role === "SALES_REP" ? <span className="text-ink-secondary">Looks after {dealersOf(u.id).length} dealer{dealersOf(u.id).length === 1 ? "" : "s"}</span> : "—") },
        { key: "s", mobile: "status", header: "Status", cell: (u) => locked(u)
          ? <Badge value="ON_HOLD" label="Locked" />
          : <Badge value={u.is_active ? "ACTIVE" : "CLOSED"} label={u.is_active ? "Active" : "Inactive"} /> },
      ]} />
      <Modal open={!!edit} title={edit?.id ? `Edit ${edit.email}` : "New user"} onClose={() => setEdit(null)}
        footer={<>
          {edit?.id && edit.is_active && !edit.reseller_id && <Button className="mr-auto" onClick={() => setHandover(edit as UserOut)}>Hand over…</Button>}
          <Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" disabled={action.busy} onClick={save}>Save</Button></>}>
        <Alert>{action.error}</Alert>
        {edit?.id && locked(edit) && (
          <Alert tone="warn">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>Locked after too many wrong passwords, until {fmtDateTime(edit.locked_until!)}.</span>
              <Button size="sm" onClick={() => unlock(edit as UserOut)}>Unlock now</Button>
            </div>
          </Alert>
        )}
        {edit && <div className="space-y-3">
          {!edit.id && <Field label="Email" required>{(id) => <Input id={id} type="email" value={edit.email ?? ""} onChange={(e) => setEdit({ ...edit, email: e.target.value })} />}</Field>}
          <Field label="Full name" required>{(id) => <Input id={id} value={edit.full_name ?? ""} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} />}</Field>
          <Field label="Phone" hint="Optional. Shown to dealers as a contact on their stock checks.">{(id) => <Input id={id} type="tel" value={edit.phone ?? ""} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} />}</Field>
          <Field label="Role">{(id) => <Select id={id} value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })} options={ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))} />}</Field>
          {edit.role === "RESELLER" && <Field label="Dealer" required hint="Dealer users only ever see this dealer's data.">{(id) => <ResellerSelect id={id} value={edit.reseller_id ?? ""} onChange={(v) => setEdit({ ...edit, reseller_id: v === "" ? null : v })} placeholder="Select…" />}</Field>}
          <Field label={edit.id ? "New password (leave blank to keep)" : "Password"} required={!edit.id} hint="10 to 72 characters; any letters, numbers, spaces or symbols. Setting a password also unlocks the account.">{(id) => <Input id={id} type="password" autoComplete="new-password" value={edit.password ?? ""} onChange={(e) => setEdit({ ...edit, password: e.target.value })} />}</Field>
          {!edit.id && edit.role !== "RESELLER" && (
            <fieldset className="rounded-control border border-line p-3">
              <label className="flex items-center gap-2 text-body font-medium">
                <input type="checkbox" className="size-4 accent-ink" checked={replaces.on}
                  onChange={(e) => setReplaces({ ...replaces, on: e.target.checked })} />
                Is this person replacing someone?
              </label>
              {replaces.on && <div className="mt-3 space-y-3">
                <Field label={`Who (${ROLE_LABELS[edit.role as RoleCode] ?? "same role"})`} required>
                  {(id) => <Select id={id} value={replaces.user} placeholder={colleagues.length ? "Choose…" : "No one with this role"}
                    onChange={(e) => setReplaces({ ...replaces, user: e.target.value ? Number(e.target.value) : "", dealers: [] })}
                    options={colleagues.map((u) => ({ value: u.id, label: `${u.full_name}${u.role === "SALES_REP" ? ` · looks after ${dealersOf(u.id).length} dealer(s)` : ""}` }))} />}
                </Field>
                <div className="space-y-2 text-body">
                  <label className="flex items-start gap-2"><input type="radio" name="replace-mode" className="mt-1 size-4 accent-ink" checked={replaces.mode === "TAKE_OVER"}
                    onChange={() => setReplaces({ ...replaces, mode: "TAKE_OVER" })} />
                    <span><b className="font-medium">Take over everything</b> (the other person is leaving): their dealers, hand-overs and approvals move to the new person, and the other login is deactivated.</span></label>
                  <label className="flex items-start gap-2"><input type="radio" name="replace-mode" className="mt-1 size-4 accent-ink" checked={replaces.mode === "SHARE"}
                    onChange={() => setReplaces({ ...replaces, mode: "SHARE" })} />
                    <span><b className="font-medium">Work alongside</b>: choose the dealers to share with the new person.</span></label>
                </div>
                {replaces.mode === "SHARE" && replaces.user !== "" && (
                  <div className="max-h-48 space-y-1 overflow-y-auto rounded-control border border-line p-2 text-label">
                    {dealersOf(replaces.user).length === 0 && <p className="text-ink-muted">They don&apos;t look after any dealers.</p>}
                    {dealersOf(replaces.user).map((r) => (
                      <label key={r.id} className="flex items-center gap-2">
                        <input type="checkbox" className="size-4 accent-ink" checked={replaces.dealers.includes(r.id)}
                          onChange={(e) => setReplaces({ ...replaces, dealers: e.target.checked ? [...replaces.dealers, r.id] : replaces.dealers.filter((x) => x !== r.id) })} />
                        {r.business_name} <span className="sku text-label text-ink-secondary">{r.account_ref}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>}
            </fieldset>
          )}
          {edit.id && <Field label="Status">{(id) => <Select id={id} value={String(edit.is_active)} onChange={(e) => setEdit({ ...edit, is_active: e.target.value === "true" })} options={[{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }]} />}</Field>}
        </div>}
      </Modal>
      {handover && <HandoverDialog from={handover} colleagues={(data ?? []).filter((u) => u.is_active && !u.reseller_id && u.role === handover.role && u.id !== handover.id)}
        dealers={dealersOf(handover.id)} onClose={() => setHandover(null)}
        onDone={() => { setHandover(null); setEdit(null); reload(); invalidateReference(); }} />}
    </Card>
  );
}

/** Hand a person's dealers, hand-overs and approvals to a colleague with the same role (finding 32, D9). */
function HandoverDialog({ from, colleagues, dealers, onClose, onDone }: {
  from: UserOut; colleagues: UserOut[]; dealers: { id: number; business_name: string; account_ref: string }[];
  onClose: () => void; onDone: () => void;
}) {
  const [to, setTo] = useState<number | "">("");
  const [all, setAll] = useState(true);
  const [chosen, setChosen] = useState<number[]>([]);
  const [deactivate, setDeactivate] = useState(true);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const action = useAction();
  const ready = to !== "" && reason.trim().length >= 3 && (all || chosen.length > 0);
  return (
    <Modal open title={`Hand over from ${from.full_name}`} onClose={done ? onDone : onClose}
      description="Their dealers, the deliveries and transfers they are carrying, and approvals waiting for them move to the person you choose. Nothing is lost."
      footer={done ? <Button variant="primary" onClick={onDone}>Close</Button> : <><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={action.busy || !ready} onClick={async () => {
          const r = await action.run(() => api.post<{ summary: string; deactivated: boolean }>(`/users/${from.id}/handover`, {
            to_user_id: to, reseller_ids: all ? null : chosen, deactivate: all && deactivate, reason: reason.trim() }));
          if (r) setDone(`${r.summary || "Nothing was open."}${r.deactivated ? ` ${from.full_name} can no longer sign in.` : ""}`);
        }}>{action.busy ? "Handing over…" : "Hand over"}</Button></>}>
      <Alert>{action.error}</Alert>
      {done ? <Alert tone="success" title="Handed over">{done}</Alert> : <>
        <Field label={`To (${ROLE_LABELS[from.role as RoleCode] ?? "same role"})`} required>
          {(id) => <Select id={id} value={to} placeholder={colleagues.length ? "Choose…" : "No one else has this role"}
            onChange={(e) => setTo(e.target.value ? Number(e.target.value) : "")} options={colleagues.map((u) => ({ value: u.id, label: u.full_name }))} />}
        </Field>
        <div className="space-y-2 text-body">
          <label className="flex items-center gap-2"><input type="radio" name="handover-scope" className="size-4 accent-ink" checked={all} onChange={() => setAll(true)} />
            Everything{from.role === "SALES_REP" ? ` (${dealers.length} dealer${dealers.length === 1 ? "" : "s"}, hand-overs and approvals)` : " (hand-overs and approvals)"}</label>
          {dealers.length > 0 && <label className="flex items-center gap-2"><input type="radio" name="handover-scope" className="size-4 accent-ink" checked={!all} onChange={() => setAll(false)} />
            Only some dealers (share the work)</label>}
        </div>
        {!all && (
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-control border border-line p-2 text-label">
            {dealers.map((r) => (
              <label key={r.id} className="flex items-center gap-2">
                <input type="checkbox" className="size-4 accent-ink" checked={chosen.includes(r.id)}
                  onChange={(e) => setChosen(e.target.checked ? [...chosen, r.id] : chosen.filter((x) => x !== r.id))} />
                {r.business_name} <span className="sku text-label text-ink-secondary">{r.account_ref}</span>
              </label>
            ))}
          </div>
        )}
        {all && <label className="flex items-center gap-2 text-body"><input type="checkbox" className="size-4 accent-ink" checked={deactivate} onChange={(e) => setDeactivate(e.target.checked)} />
          {from.full_name} is leaving: deactivate their login</label>}
        <Field label="Reason" required>{(id) => <Textarea id={id} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Resigned; last day Friday" />}</Field>
      </>}
    </Modal>
  );
}


function TaxRates() {
  const { can } = useAuth();
  const { data, reload } = useApi<TaxRate[]>("/tax-rates");
  const [edit, setEdit] = useState<Partial<TaxRate> | null>(null);
  const action = useAction();
  return (
    <Card padded={false} title="Tax rates" actions={can("pricing.write") && <Button size="sm" onClick={() => setEdit({ is_default: false, is_active: true, rate: "0.1000" })}>New rate</Button>}>
      <p className="px-4 pt-3 text-body text-ink-secondary">Rates are configuration, not code. The default applies unless a dealer has an override. Sales and invoices store the rate used at the time.</p>
      <DataTable search={false} rows={data} rowKey={(t) => t.id} onRowClick={can("pricing.write") ? (t) => setEdit({ ...t }) : undefined} columns={[
        { key: "c", header: "Code", cell: (t) => t.code }, { key: "n", header: "Name", cell: (t) => t.name },
        { key: "r", header: "Rate", align: "right", cell: (t) => `${(Number(t.rate) * 100).toFixed(2)}%` },
        { key: "d", header: "Default", cell: (t) => (t.is_default ? <Badge value="ACTIVE" label="Default" /> : "") },
      ]} />
      <Modal open={!!edit} title={edit?.id ? `Edit ${edit.code}` : "New tax rate"} onClose={() => setEdit(null)}
        footer={<><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" disabled={action.busy} onClick={async () => {
          const body = { code: edit!.code, name: edit!.name, rate: edit!.rate, is_default: edit!.is_default, is_active: edit!.is_active };
          if (await action.run(() => (edit!.id ? api.put(`/tax-rates/${edit!.id}`, body) : api.post("/tax-rates", body)))) { setEdit(null); reload(); } }}>Save</Button></>}>
        <Alert>{action.error}</Alert>
        {edit && <div className="grid grid-cols-2 gap-3">
          <Field label="Code">{(id) => <Input id={id} value={edit.code ?? ""} onChange={(e) => setEdit({ ...edit, code: e.target.value })} />}</Field>
          <Field label="Name">{(id) => <Input id={id} value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />}</Field>
          <Field label="Rate (fraction, 0.1 = 10%)">{(id) => <Input id={id} type="number" step="0.0001" min={0} max={0.9999} value={edit.rate ?? ""} onChange={(e) => setEdit({ ...edit, rate: e.target.value })} />}</Field>
          <Field label="Default">{(id) => <Select id={id} value={String(edit.is_default)} onChange={(e) => setEdit({ ...edit, is_default: e.target.value === "true" })} options={[{ value: "false", label: "No" }, { value: "true", label: "Yes" }]} />}</Field>
        </div>}
      </Modal>
    </Card>
  );
}

function Warehouses() {
  const { can } = useAuth();
  const { data, reload } = useApi<Location[]>("/locations", { type: ["WAREHOUSE"] });
  const [form, setForm] = useState({ code: "", name: "", city: "" });
  const action = useAction();
  return (
    <Card padded={false} title="Warehouses">
      <DataTable search={false} rows={data} rowKey={(l) => l.id} columns={[
        { key: "c", header: "Code", cell: (l) => l.code }, { key: "n", header: "Name", cell: (l) => l.name }, { key: "ci", header: "City", cell: (l) => l.city ?? "—" },
        { key: "d", header: "Default", cell: (l) => (l.is_default_warehouse ? <Badge value="ACTIVE" label="Default" /> : "") },
      ]} />
      {can("location.manage") && (
        <div className="flex flex-wrap items-end gap-2 border-t border-line p-3">
          <div className="w-32"><Field label="Code">{(id) => <Input id={id} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />}</Field></div>
          <div className="w-56"><Field label="Name">{(id) => <Input id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field></div>
          <div className="w-40"><Field label="City">{(id) => <Input id={id} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />}</Field></div>
          <Button variant="primary" disabled={action.busy || !form.code || !form.name} onClick={async () => { if (await action.run(() => api.post("/warehouses", { ...form, city: form.city || null }))) { setForm({ code: "", name: "", city: "" }); reload(); invalidateReference(); } }}>Add warehouse</Button>
          <div className="w-full"><Alert>{action.error}</Alert></div>
        </div>
      )}
    </Card>
  );
}

function Audit() {
  const [action, setAction] = useState("");
  const { data, error } = useApi<AuditEvent[]>("/audit-events", { action, limit: 500 });
  return (
    <Card padded={false} title="Audit log">
      <Alert>{error}</Alert>
      <DataTable label="Change history" rows={data} rowKey={(e) => e.id} pageSize={100}
        filterCount={action ? 1 : 0} onClearFilters={() => setAction("")}
        filters={<FilterField label="Action prefix" className="w-48"><Input aria-label="Action prefix" placeholder="Action prefix e.g. transfer." value={action} onChange={(e) => setAction(e.target.value)} /></FilterField>}
        columns={[
          { key: "t", pin: true, header: "When", value: (e) => e.occurred_at, cell: (e) => <span className="whitespace-nowrap text-caption">{fmtDateTime(e.occurred_at)}</span> },
          { key: "u", header: "User", value: (e) => e.actor_name, cell: (e) => e.actor_name ?? "system" },
          { key: "a", header: "Action", value: (e) => e.action, cell: (e) => <span className="sku text-label">{e.action}</span> },
          { key: "s", header: "Summary", className: "min-w-72 whitespace-normal", value: (e) => e.summary, cell: (e) => e.summary },
        ]} />
    </Card>
  );
}

function Reconcile() {
  const { data, error, reload, loading } = useApi<Reconciliation>("/inventory/reconciliation");
  return (
    <Card title="Ledger reconciliation" actions={<Button size="sm" onClick={reload} disabled={loading}>Re-run</Button>}>
      <Alert>{error}</Alert>
      <p className="mb-3 text-body text-ink-secondary">Rebuilds every stock balance from the append-only movement history and compares it with the recorded balances. Also checks that every transaction balances (stock is conserved).</p>
      {data && (data.balanced
        ? <Alert tone="success">Balanced — all recorded balances agree with the movement history (checked {fmtDateTime(data.checked_at)}).</Alert>
        : <><Alert>Differences found. Investigate before posting further adjustments.</Alert>
          <pre className="overflow-auto rounded bg-neutral-soft p-3 text-caption">{JSON.stringify(data, null, 2)}</pre></>)}
    </Card>
  );
}

interface FeedbackRow { id: number; user_name: string | null; role: string; page: string; feedback_type: string; description: string; created_at: string }

const FEEDBACK_TONES: Record<string, "critical" | "info" | "accent" | "neutral"> = { ISSUE: "critical", IMPROVEMENT: "accent", QUESTION: "info", OTHER: "neutral" };

function Feedback() {
  const { data, error } = useApi<FeedbackRow[]>("/feedback");
  return (
    <Card padded={false} title="Pilot feedback" subtitle="Submitted from the user menu by every pilot role">
      <Alert>{error}</Alert>
      <DataTable mobile="cards" label="Pilot feedback" rows={data} rowKey={(f) => f.id} searchPlaceholder="Search feedback…" empty="No feedback yet"
        emptyHint="Feedback sent through “Pilot feedback” in the user menu appears here."
        columns={[
          { key: "t", mobile: "primary", header: "When", value: (f) => f.created_at, cell: (f) => <span className="text-ink-secondary">{fmtDateTime(f.created_at)}</span> },
          { key: "k", mobile: "status", header: "Type", value: (f) => f.feedback_type, cell: (f) => <Badge value={f.feedback_type} tone={FEEDBACK_TONES[f.feedback_type]} /> },
          { key: "u", mobile: "secondary", mobileOrder: 1, header: "From", value: (f) => `${f.user_name} ${f.role}`, cell: (f) => <div><div>{f.user_name}</div><div className="text-caption text-ink-muted">{ROLE_LABELS[f.role as RoleCode] ?? f.role}</div></div> },
          { key: "p", mobile: "field", mobileOrder: 3, header: "Page", value: (f) => f.page, cell: (f) => <span className="text-ink-secondary">{f.page}</span> },
          { key: "d", mobile: "secondary", mobileOrder: 2, header: "Description", value: (f) => f.description, className: "min-w-80 whitespace-normal", cell: (f) => f.description },
        ]} />
    </Card>
  );
}

/** Keys for the customer website's server to read warehouse stock status (In stock / Low / Out). Administrators only. */
function WebsiteAccess() {
  const { data, error, reload } = useApi<PartnerKey[]>("/partner-keys");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("Customer website");
  const [created, setCreated] = useState<PartnerKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<PartnerKey | null>(null);
  const action = useAction();
  async function create() {
    const k = await action.run(() => api.post<PartnerKey>("/partner-keys", { name: name.trim() }));
    if (k) { setCreating(false); setCreated(k); setCopied(false); reload(); }
  }
  async function revoke() {
    if (!revoking) return;
    if (await action.run(() => api.post(`/partner-keys/${revoking.id}/revoke`))) { setRevoking(null); reload(); }
  }
  return (
    <>
      <Card padded={false} title="Website access"
        subtitle="Keys for the customer website's server. With a key it can read whether each SKU is In stock, Low or Out in the warehouse. It never sees quantities, dealers or prices."
        actions={<Button variant="primary" size="sm" onClick={() => { setName("Customer website"); action.setError(null); setCreating(true); }}>New key</Button>}>
        <Alert>{error}</Alert>
        <DataTable mobile="cards" label="Website access keys" search={false} rows={data} rowKey={(k) => k.id} empty="No keys yet"
          emptyHint="Create a key and give it to your website developer. They keep it on the website's server, never in the browser."
          columns={[
            { key: "n", mobile: "primary", header: "Name", cell: (k) => <span className="font-medium">{k.name}</span> },
            { key: "s", mobile: "status", header: "Status", cell: (k) => k.revoked_at ? <Badge value="CLOSED" label="Revoked" /> : <Badge value="ACTIVE" label="Active" /> },
            { key: "p", mobile: "secondary", header: "Key", cell: (k) => <span className="sku text-ink-secondary">{k.key_prefix}…</span> },
            { key: "c", mobile: "field", mobileOrder: 1, header: "Created", cell: (k) => <span className="text-ink-secondary">{fmtDateTime(k.created_at)}{k.created_by ? ` · ${k.created_by}` : ""}</span> },
            { key: "u", mobile: "field", mobileOrder: 2, header: "Last used", cell: (k) => <span className="text-ink-secondary">{k.last_used_at ? fmtDateTime(k.last_used_at) : "Never"}</span> },
            { key: "a", mobile: "action", header: <span className="sr-only">Actions</span>, cell: (k) => !k.revoked_at &&
              <Button size="sm" variant="ghost" onClick={() => { action.setError(null); setRevoking(k); }}>Revoke {k.name}</Button> },
          ]} />
      </Card>
      <Modal open={creating} title="New website access key" onClose={() => setCreating(false)}
        footer={<><Button onClick={() => setCreating(false)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || name.trim().length < 2} onClick={create}>Create key</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label="Name" hint="So you can tell keys apart, for example “Customer website”.">
          {(id, describedBy) => <Input id={id} aria-describedby={describedBy} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
      </Modal>
      <Modal open={!!created} title="Copy this key now" onClose={() => setCreated(null)}
        description="It is shown only once. If it is lost, revoke it and create a new one."
        footer={<Button variant="primary" onClick={() => setCreated(null)}>Done</Button>}>
        <Field label="Website access key">
          {(id) => <Input id={id} readOnly value={created?.key ?? ""} className="sku" onFocus={(e) => e.currentTarget.select()} />}
        </Field>
        <Button onClick={() => { void navigator.clipboard?.writeText(created?.key ?? "").then(() => setCopied(true)); }}>{copied ? "Copied" : "Copy key"}</Button>
        <p className="text-body text-ink-secondary">Give it to your website developer. The website&rsquo;s server sends it in the <span className="sku">X-API-Key</span> header. See the guide <span className="sku">docs/PARTNER_API.md</span>.</p>
      </Modal>
      <ConfirmDialog open={!!revoking} title={`Revoke ${revoking?.name ?? "key"}`} danger confirmLabel="Revoke key" busy={action.busy} error={action.error}
        message="The website stops getting stock status with this key straight away. Create a new key first if the website should keep working."
        onClose={() => setRevoking(null)} onConfirm={revoke} />
    </>
  );
}
