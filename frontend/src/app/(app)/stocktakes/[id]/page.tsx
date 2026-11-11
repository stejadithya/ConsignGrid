"use client";

import { ArrowDown, ArrowUp, Mail, Phone, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import {
  Alert, Badge, Button, Card, ConfirmDialog, cx, DataTable, DefinitionList, Field, Input, Loading, MetricStrip,
  MobileActionBar, Modal, MoreMenu, type MoreMenuItem, PageHeader, ProductCell, Qty, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Stocktake, StocktakeLine } from "@/lib/types";

interface Contact { role: string; name: string; email: string; phone: string | null }
import { StocktakeHeader } from "@/components/StocktakeHeader";
import { branding } from "@/config/branding";
import { vocab } from "@/lib/terms";

export default function StocktakeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can, user } = useAuth();
  const { data: st, error, reload, setData } = useApi<Stocktake>(`/stocktakes/${id}`);
  const { data: people } = useApi<Contact[]>(`/stocktakes/${id}/contacts`);
  const [draft, setDraft] = useState<Record<number, { sold: string; missing: string }>>({});
  const [confirm, setConfirm] = useState<"approve" | "cancel" | "recheck" | "dispute" | "recount" | null>(null);
  const [text, setText] = useState("");
  const action = useAction();

  if (error) return <Alert>{error}</Alert>;
  if (!st) return <Loading />;
  const submitted = st.status === "SUBMITTED";   // legacy counts (before reseller confirmation)
  const awaiting = st.status === "AWAITING_RESELLER";
  // Tyres not found and not yet resolved; re-check requested or disputed pause the find window (D3).
  const open = awaiting || st.status === "RECHECK_REQUESTED" || st.status === "DISPUTED";
  const isOwnReseller = !!user?.reseller_id && user.reseller_id === st.reseller_id;
  const dealerCanAct = isOwnReseller && can("stocktake.confirm");
  const canConfirm = open && (dealerCanAct || (!user?.reseller_id && can("stocktake.approve")));
  const canRecount = open && !user?.reseller_id && can("stocktake.record");
  const close = () => { setConfirm(null); setText(""); action.setError(null); };
  const post = async (path: string, body: unknown = {}) => {
    const r = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/${path}`, body));
    if (r) { close(); setData(r); }
    return r;
  };
  const unclassified = st.lines.filter((l) => !l.classified).length;

  async function classify(l: StocktakeLine) {
    const d = draft[l.id] ?? { sold: String(l.qty_sold), missing: String(l.qty_missing) };
    const res = await action.run(() => api.post<Stocktake>(`/stocktakes/${st!.id}/lines/${l.id}/classify`, { qty_sold: Number(d.sold || 0), qty_missing: Number(d.missing || 0) }));
    if (res) setData(res);
  }

  // Phones and tablets in portrait: the first next action in the bottom bar, the rest in "More" (desktop order,
  // Cancel last).
  const submitNow = async () => { const r = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/submit`)); if (r) setData(r); };
  const primaries = [
    st.status === "DRAFT" && can("stocktake.record") && { label: "Submit count", disabled: action.busy, onSelect: submitNow },
    submitted && can("stocktake.approve") && { label: "Approve & post", disabled: unclassified > 0, onSelect: () => setConfirm("approve") },
    awaiting && dealerCanAct && { label: "I found them, please re-check", onSelect: () => setConfirm("recheck") },
    canRecount && { label: "Start re-count", icon: RotateCcw, onSelect: () => setConfirm("recount") },
  ].filter((x) => !!x);
  const [first, ...otherPrimaries] = primaries;
  const NextIcon = first?.icon;
  const more: MoreMenuItem[] = [
    ...(awaiting && dealerCanAct ? [{ label: "Raise a dispute", onSelect: () => setConfirm("dispute") }] : []),
    ...otherPrimaries,
    ...((st.status === "DRAFT" || submitted || open) && can("stocktake.record") ? [{ label: "Cancel stocktake", danger: true, onSelect: () => setConfirm("cancel") }] : []),
  ];

  return (
    <>
      <PageHeader mobileActions={<MoreMenu items={more} />} title={<span className="flex items-center gap-2">Stocktake {st.number} <Badge value={st.status} /></span>}
        subtitle={<>{st.reseller_name} · {st.location_name ?? st.location_code}{st.location_city ? `, ${st.location_city}` : ""} · counted {fmtDate(st.count_date)} by {st.counted_by}</>}
        actions={<>
          {st.status === "DRAFT" && can("stocktake.record") && <Button variant="primary" disabled={action.busy} onClick={async () => { const r = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/submit`)); if (r) setData(r); }}>Submit count</Button>}
          {submitted && can("stocktake.approve") && <Button variant="primary" disabled={unclassified > 0} onClick={() => setConfirm("approve")}>Approve & post</Button>}
          {awaiting && dealerCanAct && <>
            <Button onClick={() => setConfirm("dispute")}>Raise a dispute</Button>
            <Button variant="primary" onClick={() => setConfirm("recheck")}>I found them, please re-check</Button>
          </>}
          {canRecount && <Button variant="primary" onClick={() => setConfirm("recount")}><RotateCcw aria-hidden />Start re-count</Button>}
          {(st.status === "DRAFT" || submitted || open) && can("stocktake.record") && <Button variant="ghost" onClick={() => setConfirm("cancel")}>Cancel stocktake</Button>}
        </>} />
      <Alert>{action.error}</Alert>
      <StocktakeHeader dealer={user?.reseller_id ? st.reseller_name : <Link className="link" href={`/resellers/${st.reseller_id}`}>{st.reseller_name}</Link>}
        accountRef={st.account_ref} shop={st.location_name} code={st.location_code} address={st.location_address} city={st.location_city} rep={st.sales_rep} />
      {st.recount_of_id && <Alert tone="info">This is a re-count of <Link className="underline" href={`/stocktakes/${st.recount_of_id}`}>{st.recount_of_number}</Link>.</Alert>}
      {st.status === "SUPERSEDED" && <Alert tone="info">Re-counted{st.superseded_by_id ? <> in <Link className="underline" href={`/stocktakes/${st.superseded_by_id}`}>{st.superseded_by_number}</Link></> : ""}. The {vocab.items} this check held are free again.</Alert>}
      {awaiting && (
        <Alert tone={st.overdue ? "error" : "warn"} title={isOwnReseller ? `Some ${vocab.items} weren't found` : `Waiting for the ${vocab.partner}`}>
          {st.total_shortage} {vocab.item}(s) weren&apos;t found at the stock check.{" "}
          {isOwnReseller ? <>You have {st.find_days ?? 5} days to find them. If you find them, ask for a re-check. If not, they&apos;ll be invoiced as sold on <b>{fmtDate(st.confirm_due_at)}</b>.</>
            : <>The {vocab.partner} has until <b>{fmtDate(st.confirm_due_at)}</b> to find them or ask for a re-check; then they are invoiced as sold automatically.</>}
          {st.reminder_count ? ` ${st.reminder_count} reminder(s) sent.` : ""} They are held meanwhile so they cannot be sold or moved.
        </Alert>
      )}
      {st.status === "RECHECK_REQUESTED" && (
        <Alert tone="info" title="Re-check requested">
          {st.recheck_requested_by ?? `The ${vocab.partner}`} found the {vocab.items} on {fmtDateTime(st.recheck_requested_at)}{st.recheck_note ? `: “${st.recheck_note}”` : ""}.
          {isOwnReseller ? " Your sales rep or the warehouse will re-count them. Nothing will be invoiced meanwhile." : " Start a re-count when you visit. The automatic invoicing is paused."}
        </Alert>
      )}
      {st.status === "DISPUTED" && (
        <Alert tone="warn" title="Disputed">
          {st.disputed_by ?? `The ${vocab.partner}`} raised a dispute on {fmtDateTime(st.disputed_at)}: “{st.dispute_note}”.
          {isOwnReseller ? " The warehouse and your Relationship Manager will contact you. Nothing will be invoiced meanwhile." : ` Follow up with the ${vocab.partner}: start a re-count, or invoice the shortage with a reason. The automatic invoicing is paused.`}
        </Alert>
      )}
      {people && people.length > 0 && <Contacts people={people} />}
      {canConfirm && <ConfirmShortages st={st} onDone={setData} onBehalf={!isOwnReseller} />}
      {st.status === "APPROVED" && st.invoice_id && (
        <Alert tone="info">The {vocab.items} not found were invoiced as sold: invoice record{" "}
          {can("invoice.read") && st.invoice_number ? <Link className="underline" href={`/invoices/${st.invoice_id}`}>{st.invoice_number}</Link> : "created"}
          {can("invoice.create") ? ", to mark as invoiced in Xero" : ""}. Replacements were raised.
          {st.confirmed_on_behalf_reason ? ` ${st.confirmed_on_behalf_reason.startsWith("Automatically") ? st.confirmed_on_behalf_reason : `Confirmed on the ${vocab.partner}'s behalf: ${st.confirmed_on_behalf_reason}`}.` : ""}</Alert>
      )}
      {submitted && unclassified > 0 && <Alert tone="warn">{unclassified} line(s) have an unclassified shortage. Classify each shortage as sold (chargeable) or missing (loss) — missing stock is never assumed sold.</Alert>}
      {st.status === "APPROVED" && <Alert tone="success">{st.total_shortage ? "Confirmed" : "Posted"} by {st.approved_by ?? `${branding.productName} (automatically)`} on {fmtDateTime(st.approved_at)}. {st.sale_id ? <Link className="underline" href={`/sales?sale=${st.sale_id}`}>View the resulting sale</Link> : "No sales were confirmed."}</Alert>}
      <MetricStrip items={[
        { label: "Expected", value: st.lines.reduce((a, l) => a + (l.expected_qty ?? 0), 0), hint: `${st.lines.length} SKUs` },
        { label: "Counted", value: st.lines.reduce((a, l) => a + l.counted_qty, 0), hint: `${st.lines.reduce((a, l) => a + l.counted_damaged_qty, 0)} damaged` },
        { label: "Net variance", value: `${st.total_variance > 0 ? "+" : ""}${st.total_variance}`, tone: st.total_variance < 0 ? "danger" : st.total_variance > 0 ? "ok" : "default" },
        awaiting
          ? { label: `Not found, awaiting ${vocab.partner}`, value: st.total_shortage ?? 0, tone: st.overdue ? "danger" : "warn", hint: `Due ${fmtDateTime(st.confirm_due_at)}` }
          : { label: "Shortages to classify", value: unclassified, tone: unclassified ? "warn" : "default", hint: "Sold or missing — never assumed sold" },
      ]} />
      <Card padded={false} title="Count lines" subtitle="Expected vs counted quantity per SKU">
        <DataTable mobile="cards" density="comfortable" label={`Counted ${vocab.items}`} search={false} rows={st.lines} rowKey={(l) => l.id}
          columns={[
            { key: "sku", mobile: "primary", header: "Product", cell: (l) => <ProductCell name={l.product_name} sku={l.sku} /> },
            { key: "e", mobile: "field", mobileOrder: 1, header: "Expected", align: "right", cell: (l) => <Qty value={l.expected_qty} zeroMuted={false} /> },
            { key: "c", mobile: "field", mobileOrder: 2, header: "Counted", align: "right", cell: (l) => <Qty value={l.counted_qty} zeroMuted={false} /> },
            { key: "dm", header: "Damaged", align: "right", cell: (l) => <Qty value={l.counted_damaged_qty} tone="warn" /> },
            { key: "v", mobile: "field", mobileOrder: 3, header: "Variance", align: "right", cell: (l) => l.variance === null ? "—" : l.variance === 0
              ? <span className="text-ink-muted">0</span>
              : <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold ring-1 ring-inset", l.variance < 0 ? "bg-danger-soft text-danger ring-danger-line" : "bg-success-soft text-success ring-success-line")}>
                  {l.variance < 0 ? <ArrowDown className="size-3" aria-label="short" /> : <ArrowUp className="size-3" aria-label="over" />}{l.variance > 0 ? "+" : ""}{l.variance}
                </span> },
            { key: "cls", mobile: "field", mobileLabel: "Classification", mobileOrder: 4, header: "Shortage classification", cell: (l) => l.shortage === 0 ? <span className="text-caption text-ink-muted">{l.variance && l.variance > 0 ? "Surplus → approved gain" : "—"}</span> : submitted && can("stocktake.record") ? (
              <div className="flex flex-wrap items-center gap-2 text-caption">
                <label className="flex items-center gap-1.5 text-ink-secondary">Sold <Input className="w-16" type="number" min={0} value={draft[l.id]?.sold ?? String(l.qty_sold)} onChange={(e) => setDraft((d) => ({ ...d, [l.id]: { sold: e.target.value, missing: d[l.id]?.missing ?? String(l.qty_missing) } }))} /></label>
                <label className="flex items-center gap-1.5 text-ink-secondary">Missing <Input className="w-16" type="number" min={0} value={draft[l.id]?.missing ?? String(l.qty_missing)} onChange={(e) => setDraft((d) => ({ ...d, [l.id]: { missing: e.target.value, sold: d[l.id]?.sold ?? String(l.qty_sold) } }))} /></label>
                <Button size="sm" onClick={() => classify(l)}>Save</Button>
                {l.classified ? <Badge value="FULFILLED" label="Classified" /> : <Badge value="ACTION_REQUIRED" label={`${l.shortage} to classify`} />}
              </div>
            ) : <span className="text-caption">{l.qty_sold ? `Invoiced as sold ${l.qty_sold}` : awaiting ? `${l.shortage} not found` : "—"}{l.qty_missing ? ` · written off ${l.qty_missing} (before 1.11)` : ""}</span> },
          ]} />
      </Card>
      <Card title="Details" className="mt-4"><DefinitionList items={[["Submitted", fmtDateTime(st.submitted_at)], ["Notes", st.notes], ["Net variance", st.total_variance]]} /></Card>
      {first && <MobileActionBar desktop="hidden">
        <Button variant="primary" disabled={first.disabled} onClick={first.onSelect}>{NextIcon && <NextIcon aria-hidden />}{first.label}</Button>
      </MobileActionBar>}
      <ConfirmDialog open={confirm === "approve"} title="Approve stocktake" busy={action.busy} error={action.error} confirmLabel="Approve and post"
        message={`This posts a confirmed sale for sold quantities (chargeable, triggers replenishment), loss adjustments for missing stock, gains for surpluses, and blocks damaged ${vocab.items}.`}
        onClose={() => setConfirm(null)}
        onConfirm={async () => { const r = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/approve`)); if (r) { setData(r); setConfirm(null); } }} />
      <Modal open={confirm === "recheck"} title="I found them, please re-check" onClose={close}
        description={`Your sales rep or the warehouse re-counts the ${vocab.items}. Nothing is invoiced while you wait.`}
        footer={<><Button onClick={close}>Back</Button><Button variant="primary" disabled={action.busy}
          onClick={() => post("request-recheck", { note: text.trim() || null })}>{action.busy ? "Sending…" : "Ask for a re-check"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label="Note" hint="Optional, e.g. where they were">{(fid) => <Textarea id={fid} rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. They were in the back store" />}</Field>
      </Modal>
      <Modal open={confirm === "dispute"} title="Raise a dispute" onClose={close}
        description="Tell us what is wrong with the count. The Warehouse Manager and your Relationship Manager will contact you; nothing is invoiced meanwhile."
        footer={<><Button onClick={close}>Back</Button><Button variant="primary" disabled={action.busy || text.trim().length < 3}
          onClick={() => post("dispute", { message: text.trim() })}>{action.busy ? "Sending…" : "Send dispute"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label="What is wrong?" required>{(fid) => <Textarea id={fid} rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Two of these were returned to the warehouse last week" />}</Field>
      </Modal>
      <ConfirmDialog open={confirm === "recount"} title="Start re-count" busy={action.busy} error={action.error} confirmLabel="Start re-count" onClose={close}
        message={`${st.number} is marked as re-counted and the ${vocab.items} it held are released. A new draft count for the same ${vocab.site} opens with the ${st.lines.filter((l) => l.shortage).length} SKU(s) that weren't found.`}
        onConfirm={async () => { const r = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/recount`)); if (r) { close(); router.push(`/stocktakes/${r.id}`); } }} />
      <ConfirmDialog open={confirm === "cancel"} title="Cancel stocktake" danger requireReason busy={action.busy} error={action.error}
        onClose={() => setConfirm(null)}
        onConfirm={async (reason) => { if (await action.run(() => api.post(`/stocktakes/${st.id}/cancel`, { reason }))) { setConfirm(null); reload(); } }} />
    </>
  );
}


/** Tyres not found: the dealer (or staff on their behalf, with a reason) has them invoiced as sold. Nothing is written
 * off as missing (finding 28); re-checks and disputes are separate actions. */
function ConfirmShortages({ st, onDone, onBehalf }: { st: Stocktake; onDone: (s: Stocktake) => void; onBehalf: boolean }) {
  const short = st.lines.filter((l) => l.shortage > 0);
  const [reason, setReason] = useState("");
  const action = useAction();
  const total = short.reduce((a, l) => a + l.shortage, 0);

  return (
    <Card className="mb-4" title={onBehalf ? `Invoice on the ${vocab.partner}'s behalf` : `${vocab.Items} not found`}
      subtitle={`These ${vocab.items} weren't on the shelf at the count. If they're not found, they are invoiced as sold and replaced.`}>
      <Alert>{action.error}</Alert>
      <div className="divide-y divide-line rounded-control border border-line">
        {short.map((l) => (
          <div key={l.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
            <ProductCell name={l.product_name} sku={l.sku} />
            <span className="ml-auto text-label text-ink-secondary"><b className="num text-ink">{l.shortage}</b> not found</span>
          </div>
        ))}
      </div>
      {onBehalf && (
        <div className="mt-3"><Field label={`Reason for invoicing on the ${vocab.partner}'s behalf`} required>
          {(id) => <Textarea id={id} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Agreed with the owner by phone" />}
        </Field></div>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
        <span className="text-label text-ink-secondary">{total} {vocab.item}(s) will be invoiced and replaced</span>
        <Button variant="primary" disabled={action.busy || (onBehalf && reason.trim().length < 3)}
          onClick={async () => {
            const res = await action.run(() => api.post<Stocktake>(`/stocktakes/${st.id}/confirm`, {
              lines: short.map((l) => ({ line_id: l.id, qty_sold: l.shortage, qty_missing: 0 })),
              on_behalf_reason: onBehalf ? reason.trim() : null,
            }));
            if (res) onDone(res);
          }}>{action.busy ? "Saving…" : onBehalf ? "Invoice the shortage" : "Not found, invoice them now"}</Button>
      </div>
    </Card>
  );
}

/** Always-visible contacts for a stock check: the warehouse, the Relationship Managers and the dealer's sales rep. */
function Contacts({ people }: { people: Contact[] }) {
  return (
    <Card className="mb-4" title="Questions? Contact us">
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {people.map((p) => (
          <li key={`${p.role}-${p.email}`} className="rounded-control border border-line px-3 py-2.5 text-label">
            <div className="font-medium text-ink">{p.name}</div>
            <div className="text-caption text-ink-muted">{p.role}</div>
            <a className="mt-1 flex items-center gap-1.5 text-ink-secondary hover:text-ink" href={`mailto:${p.email}`}><Mail className="size-3.5" aria-hidden />{p.email}</a>
            {p.phone && <a className="flex items-center gap-1.5 text-ink-secondary hover:text-ink" href={`tel:${p.phone}`}><Phone className="size-3.5" aria-hidden />{p.phone}</a>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
