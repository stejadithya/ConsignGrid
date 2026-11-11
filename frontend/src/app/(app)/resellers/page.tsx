"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Copy, Lock, Plus } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AGREEMENT_ACCEPT, uploadAgreement } from "@/components/AgreementFiles";
import { invalidateReference, useReference } from "@/components/pickers";
import {
  blankLines, importInitialStock, InitialStockFilePicker, postInitialStock, StockLinesEditor, validLines, type StockLine,
} from "@/components/InitialStock";
import {
  Alert, Badge, Button, Card, DataTable, DefinitionList, Field, FilterField, Input, MetricStrip, Modal, PageHeader,
  Qty, Select, Tabs,
} from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useApi } from "@/lib/hooks";
import type { Reseller, ResellerSummary, Stocktake, UserOut } from "@/lib/types";
import { branding } from "@/config/branding";
import { vocab } from "@/lib/terms";

interface ConsRow { reseller_id: number; on_hand: number }
interface BackRow { reseller_id: number; qty_outstanding: number; qty_awaiting_supply: number }
interface Uninv { reseller_id: number; uninvoiced_qty: number }

export default function ResellersPage() {
  const { can } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState("");
  const { data, error } = useApi<ResellerSummary[]>("/resellers", { status });
  const canReport = can("report.read");
  const { data: cons } = useApi<{ rows: ConsRow[] }>(canReport && can("inventory.read") ? "/reports/consignment-stock" : null);
  const { data: back } = useApi<{ rows: BackRow[] }>(canReport ? "/reports/backorders" : null);
  const { data: uninv } = useApi<Uninv[]>(canReport && can("invoice.read") ? "/reports/uninvoiced-sales" : null);
  const { data: stocktakes } = useApi<Stocktake[]>(can("inventory.read") ? "/stocktakes" : null);
  const params = useSearchParams();
  const [open, setOpen] = useState(params.get("new") === "1" && can("reseller.write"));

  const agg = useMemo(() => {
    const m = new Map<number, { stock: number; outstanding: number; awaiting: number; uninvQty: number; lastCount: string | null }>();
    const get = (id: number) => m.get(id) ?? (m.set(id, { stock: 0, outstanding: 0, awaiting: 0, uninvQty: 0, lastCount: null }), m.get(id)!);
    (cons?.rows ?? []).forEach((r) => { get(r.reseller_id).stock += r.on_hand; });
    (back?.rows ?? []).forEach((r) => { const a = get(r.reseller_id); a.outstanding += r.qty_outstanding; a.awaiting += r.qty_awaiting_supply; });
    (uninv ?? []).forEach((u) => { const a = get(u.reseller_id); a.uninvQty += u.uninvoiced_qty; });
    (stocktakes ?? []).forEach((st) => { const a = get(st.reseller_id); if (!a.lastCount || st.count_date > a.lastCount) a.lastCount = st.count_date; });
    return m;
  }, [cons, back, uninv, stocktakes]);
  const counts = (s: string) => (data ?? []).filter((r) => r.status === s).length;

  return (
    <>
      <PageHeader title={vocab.Partners} subtitle={`${vocab.Partner} accounts holding consignment stock, with their outstanding replenishment and uninvoiced activity.`}
        actions={can("reseller.write") && <Button variant="primary" onClick={() => setOpen(true)}><Plus aria-hidden />New {vocab.partner}</Button>} />
      <Alert>{error}</Alert>
      {data && !status && (
        <MetricStrip items={[
          { label: "Accounts", value: data.length, hint: `${data.reduce((a, r) => a + r.location_count, 0)} consignment locations` },
          { label: "Active", value: counts("ACTIVE"), tone: "ok" },
          { label: "On hold", value: counts("ON_HOLD"), tone: counts("ON_HOLD") ? "warn" : "default" },
          { label: "Closed", value: counts("CLOSED") },
        ]} />
      )}
      <Card padded={false}>
        <DataTable mobile="cards" label={vocab.Partners} rows={data} rowKey={(r) => r.id} onRowClick={(r) => router.push(`/resellers/${r.id}`)} searchPlaceholder="Search name, account, rep…"
          empty={status ? `No ${vocab.partners} with this status` : `No ${vocab.partner} accounts yet`}
          emptyHint={status ? undefined : `Create the first ${vocab.partner} account to begin consignment operations.`}
          emptyAction={!status && can("reseller.write") ? <Button size="sm" variant="primary" onClick={() => setOpen(true)}><Plus aria-hidden />New {vocab.partner}</Button> : undefined}
          filterCount={status ? 1 : 0} onClearFilters={() => setStatus("")}
          filters={<FilterField label="Status" className="w-40"><Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses"
            options={["ACTIVE", "ON_HOLD", "CLOSED"].map((s) => ({ value: s, label: s === "ON_HOLD" ? "On hold" : s.charAt(0) + s.slice(1).toLowerCase() }))} /></FilterField>}
          columns={[
            { key: "name", mobile: "primary" as const, header: vocab.Partner, mobileSort: `${vocab.Partner} name`, value: (r) => `${r.business_name} ${r.account_ref}`, cell: (r) => (
              <div className="flex items-center gap-3">
                <span aria-hidden className="inline-flex size-9 shrink-0 items-center justify-center rounded-control bg-neutral-soft text-caption font-semibold text-ink-secondary">
                  {r.business_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                </span>
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink">{r.business_name}</div>
                  <div className="text-caption text-ink-muted"><span className="sku text-label text-ink-secondary">{r.account_ref}</span>{r.sales_rep_name && <> · {r.sales_rep_name}</>}</div>
                </div>
              </div>
            ) },
            { key: "locs", header: "Locations", align: "right", value: (r) => r.location_count, cell: (r) => <span className="text-ink-secondary">{r.location_count}</span> },
            ...(cons ? [{ key: "stock", mobile: "field" as const, mobileLabel: "Stock", mobileOrder: 1, header: "Consignment stock", align: "right" as const, value: (r: ResellerSummary) => agg.get(r.id)?.stock ?? 0,
              cell: (r: ResellerSummary) => <span className="font-medium"><Qty value={agg.get(r.id)?.stock ?? 0} /></span> }] : []),
            ...(back ? [{ key: "out", mobile: "field" as const, mobileLabel: "Waiting", mobileOrder: 2, header: "Outstanding replenishment", align: "right" as const, value: (r: ResellerSummary) => agg.get(r.id)?.outstanding ?? 0,
              cell: (r: ResellerSummary) => {
                const a = agg.get(r.id);
                return a?.outstanding ? <div><Qty value={a.outstanding} /><div className="text-caption text-warning">{a.awaiting ? `${a.awaiting} awaiting supply` : "all covered"}</div></div> : <Qty value={0} />;
              } }] : []),
            ...(uninv ? [{ key: "uninv", mobile: "field" as const, mobileOrder: 3, header: "Sold, not invoiced", align: "right" as const, value: (r: ResellerSummary) => agg.get(r.id)?.uninvQty ?? 0,
              cell: (r: ResellerSummary) => {
                const a = agg.get(r.id);
                return a?.uninvQty ? <div><span className="font-medium">{a.uninvQty}</span><div className="text-caption text-ink-muted">{vocab.item}(s)</div></div> : <span className="text-ink-muted">—</span>;
              } }] : []),
            ...(stocktakes ? [{ key: "st", header: "Last stocktake", value: (r: ResellerSummary) => agg.get(r.id)?.lastCount ?? "",
              cell: (r: ResellerSummary) => <span className="text-ink-secondary">{agg.get(r.id)?.lastCount ? fmtDate(agg.get(r.id)!.lastCount) : "Never"}</span> }] : []),
            { key: "status", mobile: "status" as const, header: "Status", value: (r) => r.status, cell: (r) => <Badge value={r.status} /> },
          ]} />
      </Card>
      {open && <NewResellerModal onClose={() => setOpen(false)} onCreated={(id) => router.push(`/resellers/${id}`)} />}
    </>
  );
}

/** The dealer's new login, shown once with a Copy button (D7: never emailed). */
function LoginCreated({ login, onDone }: { login: { email: string; temporary_password: string }; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(`Email: ${login.email}\nTemporary password: ${login.temporary_password}`); setCopied(true); } catch { setCopied(false); }
  }
  return (
    <Modal open title={`${vocab.Partner} login created`} description="Shown once. Write it down or copy it now." onClose={onDone}
      footer={<Button variant="primary" onClick={onDone}>Done — open the {vocab.partner}</Button>}>
      <DefinitionList columns={1} items={[["Email (username)", <span key="e" className="sku">{login.email}</span>],
        ["Temporary password", <span key="p" className="sku text-body-lg font-semibold tracking-wide" data-testid="temporary-password">{login.temporary_password}</span>]]} />
      <Button onClick={copy}><Copy aria-hidden />{copied ? "Copied" : "Copy"}</Button>
      <Alert tone="info">Share privately (phone or in person), not in a group chat or by email. The {vocab.partner} chooses their own password when they first sign in.</Alert>
    </Modal>
  );
}

interface Shop { name: string; address_line1: string; address_line2: string; city: string; postcode: string; contact_phone: string }
const blankShop = (): Shop => ({ name: "", address_line1: "", address_line2: "", city: "", postcode: "", contact_phone: "" });

function NewResellerModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const { can } = useAuth();
  const canLogin = can("user.manage");
  const [withLogin, setWithLogin] = useState(true);   // D7: ticked by default
  const [login, setLogin] = useState<{ id: number; email: string; temporary_password: string } | null>(null);
  const reps = useReference<UserOut[]>("/staff", { role: "SALES_REP" });
  const [f, setF] = useState({ business_name: "", trading_name: "", contact_name: "", email: "", phone: "", billing_address: "",
    sales_rep_user_id: "", payment_terms_days: "30", agreement_reference: "", transfer_consent: "PER_TRANSFER",
  });
  const [shops, setShops] = useState<Shop[]>([blankShop()]);
  const setShop = (i: number, k: keyof Shop) => (e: { target: { value: string } }) =>
    setShops((all) => all.map((s, j) => (j === i ? { ...s, [k]: e.target.value } : s)));
  const [existing, setExisting] = useState(false);   // already trading with the supplier and holding stock
  const [lines, setLines] = useState<StockLine[]>(blankLines);
  const [stockMode, setStockMode] = useState("enter");
  const [stockFile, setStockFile] = useState<File | null>(null);
  const [agreementFile, setAgreementFile] = useState<File | null>(null);
  const [created, setCreated] = useState<Reseller | null>(null);
  const action = useAction();
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  // The account reference is created by the system (D4); show what it will be as the name and city are typed.
  const [preview, setPreview] = useState<string | null>(null);
  const firstCity = shops[0].city.trim();
  useEffect(() => {
    const name = f.business_name.trim();
    if (!name) return;
    const t = setTimeout(() => {
      api.get<{ account_ref: string }>("/resellers/account-ref-preview", { business_name: name, city: firstCity || undefined })
        .then((r) => setPreview(r.account_ref)).catch(() => setPreview(null));
    }, 350);
    return () => clearTimeout(t);
  }, [f.business_name, firstCity]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await action.run(() => api.post<Reseller>("/resellers", {
      business_name: f.business_name, trading_name: f.trading_name.trim() || null, contact_name: f.contact_name, email: f.email,
      phone: f.phone, billing_address: f.billing_address,
      sales_rep_user_id: f.sales_rep_user_id ? Number(f.sales_rep_user_id) : null,
      payment_terms_days: f.payment_terms_days ? Number(f.payment_terms_days) : null,
      agreement: f.agreement_reference ? { reference: f.agreement_reference, transfer_consent: f.transfer_consent } : null,
      create_login: canLogin && withLogin,
      joined_with_stock: existing,
      // Shop codes are created from the account reference: {REF}-01, -02 …
      locations: shops.map((s) => ({ name: s.name.trim() || f.business_name, address_line1: s.address_line1, address_line2: s.address_line2.trim() || null,
        city: s.city, postcode: s.postcode.trim() || null, contact_phone: s.contact_phone.trim() || null })),
    }));
    if (!r) return;
    invalidateReference();
    const stock = validLines(lines);
    if (existing && stockMode === "excel" && stockFile) {
      setCreated(r);
      if (!(await action.run(() => importInitialStock(r.id, stockFile, true)))) return;   // dealer exists; show the error
    } else if (existing && stockMode === "enter" && stock.length && r.locations[0]) {
      setCreated(r);
      if (!(await action.run(() => postInitialStock(r.id, r.locations[0].id, lines)))) return;   // reseller exists; show the error
    } else if (!existing && stock.length && r.locations[0]) {
      // A new dealer's first stock goes to the warehouse for approval, picking and delivery like any order.
      setCreated(r);
      if (!(await action.run(() => api.post("/stock-requests", { location_id: r.locations[0].id, lines: stock, submit: true,
        notes: `First order for a new ${vocab.partner}` })))) return;   // dealer exists; show the error
    }
    if (agreementFile) {
      setCreated(r);
      if (!(await action.run(() => uploadAgreement(r.id, agreementFile)))) return;   // dealer exists; show the error
    }
    if (r.login) { setLogin({ id: r.id, ...r.login }); return; }   // show the temporary password once
    onCreated(r.id);
  }
  if (login) return <LoginCreated login={login} onDone={() => onCreated(login.id)} />;
  return (
    <Modal open title={`New ${vocab.partner}`} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{action.error}</Alert>
        {created && <Alert tone="warn">{created.business_name} was created, but the stock or agreement copy was not saved. Add it from the {vocab.partner}&apos;s page
          (<button type="button" className="underline" onClick={() => onCreated(created.id)}>open {created.business_name}</button>).</Alert>}
        <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2" disabled={!!created}>
          <legend className="mb-1.5 text-label font-medium text-ink">Is this {vocab.partner} already trading with {branding.companyName}?</legend>
          {[{ v: false, t: `New ${vocab.partner}`, d: `Starting with ${branding.companyName} now. Their first order goes to the warehouse for approval, then the Sales Rep delivers it.` },
            { v: true, t: `Existing ${branding.companyName} ${vocab.partner}`, d: `Already holds stock ${branding.companyName} supplied; record it as their initial stock.` }].map((o) => (
            <label key={o.t} className={`flex cursor-pointer gap-2.5 rounded-control border p-3 ${existing === o.v ? "border-ink bg-subtle" : "border-line"}`}>
              <input type="radio" name="existing" className="mt-0.5 size-4 accent-ink" checked={existing === o.v} onChange={() => setExisting(o.v)} />
              <span><span className="block text-body font-medium">{o.t}</span><span className="block text-caption text-ink-muted">{o.d}</span></span>
            </label>
          ))}
        </fieldset>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Business name" required info="Shown on every screen and printed on delivery notes and invoices. Use the name exactly as in Xero.">
            {(id) => <Input id={id} value={f.business_name} onChange={set("business_name")} required />}</Field>
          <Field label="Account reference (automatic)" hint={`Made from the business name and the first ${vocab.site}'s city; confirmed when you save.`}
            info={`Created automatically. It identifies this ${vocab.partner} on requests, deliveries, delivery notes, invoices, Xero and reports, so it never changes.`}>
            {(id) => <div className="relative">
              <Input id={id} value={f.business_name.trim() ? preview ?? "…" : ""} disabled aria-readonly placeholder="Created from the name and city"
                className="cursor-not-allowed bg-subtle pr-9 sku text-ink-secondary" />
              <Lock className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
            </div>}
          </Field>
          <Field label="Trading name" info={`Optional ${vocab.site} sign name.`}>{(id) => <Input id={id} value={f.trading_name} onChange={set("trading_name")} />}</Field>
          <Field label="Contact name" required>{(id) => <Input id={id} value={f.contact_name} onChange={set("contact_name")} required />}</Field>
          <Field label="Email" required>{(id) => <Input id={id} type="email" value={f.email} onChange={set("email")} required />}</Field>
          <Field label="Phone" required>{(id) => <Input id={id} value={f.phone} onChange={set("phone")} required />}</Field>
          <Field label="Sales representative" required>{(id) => <Select id={id} value={f.sales_rep_user_id} onChange={set("sales_rep_user_id")} placeholder="Choose a sales rep" required
            options={(reps ?? []).map((u) => ({ value: u.id, label: u.full_name }))} />}</Field>
          <Field label="Billing address" hint={`One per ${vocab.partner}, used for invoices.`} required>{(id) => <Input id={id} value={f.billing_address} onChange={set("billing_address")} required />}</Field>
          <Field label="Payment terms (days)">{(id) => <Input id={id} type="number" min={0} value={f.payment_terms_days} onChange={set("payment_terms_days")} />}</Field>
          <Field label="Consignment agreement ref.">{(id) => <Input id={id} value={f.agreement_reference} onChange={set("agreement_reference")} />}</Field>
          <Field label="Copy of the signed agreement" hint="Optional. PDF or photo, up to 5 MB.">
            {(id) => <input id={id} type="file" accept={AGREEMENT_ACCEPT} className="block w-full text-label"
              onChange={(e) => setAgreementFile(e.target.files?.[0] ?? null)} />}</Field>
          <Field label="Transfer consent">{(id) => <Select id={id} value={f.transfer_consent} onChange={set("transfer_consent")}
            options={[{ value: "PRE_AUTHORISED", label: "Pre-authorised" }, { value: "PER_TRANSFER", label: "Consent per transfer" }, { value: "NOT_ALLOWED", label: "Transfers out not allowed" }]} />}</Field>
        </div>
        <section className="rounded-control border border-line p-3" aria-label={vocab.Sites}>
          <div className="mb-1 text-body font-medium">{vocab.Sites} (delivery locations)</div>
          <p className="mb-3 text-caption text-ink-muted">Where {vocab.items} are delivered. Each {vocab.site} gets a code from the account reference (e.g. AKT-AUC-001-01).</p>
          <div className="space-y-3">
            {shops.map((s, i) => (
              <fieldset key={i} className="grid grid-cols-1 gap-3 rounded-control bg-subtle p-3 sm:grid-cols-2">
                <legend className="sr-only">{vocab.Site} {i + 1}</legend>
                <div className="flex items-center justify-between sm:col-span-2">
                  <span className="text-label font-medium">{vocab.Site} {i + 1}{i === 0 && " (required)"}</span>
                  {i > 0 && <Button size="sm" variant="ghost" onClick={() => setShops((all) => all.filter((_, j) => j !== i))}>Remove</Button>}
                </div>
                <Field label={`${vocab.Site} ${i + 1} name`}>{(id) => <Input id={id} value={s.name} onChange={setShop(i, "name")} placeholder={f.business_name || `${vocab.Site} name`} />}</Field>
                <Field label={`${vocab.Site} ${i + 1} contact phone`}>{(id) => <Input id={id} value={s.contact_phone} onChange={setShop(i, "contact_phone")} />}</Field>
                <Field label={`${vocab.Site} ${i + 1} delivery address`} required>{(id) => <Input id={id} value={s.address_line1} onChange={setShop(i, "address_line1")} required placeholder="Address line 1" />}</Field>
                <Field label={`${vocab.Site} ${i + 1} address line 2`}>{(id) => <Input id={id} value={s.address_line2} onChange={setShop(i, "address_line2")} />}</Field>
                <Field label={`${vocab.Site} ${i + 1} city`} required>{(id) => <Input id={id} value={s.city} onChange={setShop(i, "city")} required />}</Field>
                <Field label={`${vocab.Site} ${i + 1} postcode`}>{(id) => <Input id={id} value={s.postcode} onChange={setShop(i, "postcode")} />}</Field>
              </fieldset>
            ))}
          </div>
          <Button size="sm" className="mt-3" onClick={() => setShops((all) => [...all, blankShop()])}><Plus aria-hidden />Add another {vocab.site}</Button>
        </section>
        {!existing && (
          <div className="rounded-control border border-line p-3">
            <div className="mb-2 text-body font-medium">First order (optional)</div>
            <p className="mb-3 text-caption text-ink-muted">{vocab.Items} to send to the first {vocab.site}. Saved as a stock request: the warehouse checks and approves it,
              then the Sales Rep delivers it. You can also order later from the {vocab.partner}&apos;s page.</p>
            <StockLinesEditor lines={lines} onChange={setLines} />
          </div>
        )}
        {existing && (
          <div className="rounded-control border border-line p-3">
            <div className="mb-2 text-body font-medium">Initial stock (backorder)</div>
            <p className="mb-3 text-caption text-ink-muted">{vocab.Items} this {vocab.partner} holds today. Saved to the first {vocab.site} as their consignment stock. You can also add it later from the {vocab.partner}&apos;s page.</p>
            <Tabs active={stockMode} onChange={setStockMode} tabs={[{ id: "enter", label: `Enter ${vocab.items}` }, { id: "excel", label: "Upload Excel" }]} />
            {stockMode === "excel"
              ? <><InitialStockFilePicker file={stockFile} onChange={setStockFile} />
                  <p className="mt-2 text-caption text-ink-muted">Imported when you save. If a row has a problem, nothing is imported and you can fix it from the {vocab.partner}&apos;s page.</p></>
              : <StockLinesEditor lines={lines} onChange={setLines} />}
          </div>
        )}
        {canLogin && (
          <label className="flex cursor-pointer items-start gap-2.5 rounded-control border border-line p-3">
            <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={withLogin} onChange={(e) => setWithLogin(e.target.checked)} />
            <span><span className="block text-body font-medium">Create a login for this {vocab.partner}</span>
              <span className="block text-caption text-ink-muted">Their email above becomes the username. A temporary password is shown once, after saving.</span></span>
          </label>
        )}
        {/* Phones: the form's buttons stay at the bottom of the screen while this long dialog scrolls, like a dialog footer. */}
        <div className="flex justify-end gap-2 max-sm:sticky max-sm:bottom-0 max-sm:-mx-5 max-sm:-mb-5 max-sm:rounded-b-card max-sm:border-t max-sm:border-line max-sm:bg-subtle max-sm:px-5 max-sm:pt-3 max-sm:pb-[max(0.75rem,env(safe-area-inset-bottom))]"><Button type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={action.busy || !!created}>{existing && (stockMode === "excel" ? !!stockFile : validLines(lines).length > 0) ? `Create ${vocab.partner} and add stock`
            : !existing && validLines(lines).length > 0 ? `Create ${vocab.partner} and send first order` : `Create ${vocab.partner}`}</Button></div>
      </form>
    </Modal>
  );
}
