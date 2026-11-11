"use client";

import { Plus, Send, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { CheckStockButton } from "@/components/CheckStock";
import { StockAvailability } from "@/components/StockAvailability";
import { FindForMeNote, useNeedsHelp } from "@/components/FindForMe";
import { LocationSelect, ProductSelect, useLocations } from "@/components/pickers";
import { Alert, Button, Card, Field, Input, Loading, MobileActionBar, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { StockRequestDetail } from "@/lib/types";
import { vocab } from "@/lib/terms";

interface Row { key: number; product: number | ""; qty: string; notes: string; findForMe: boolean }

let nextKey = 1;
const blankRow = (): Row => ({ key: nextKey++, product: "", qty: "", notes: "", findForMe: false });

/** Create (or edit a draft of) a multi-SKU consignment stock request. */
export default function NewStockRequestPage() {
  const params = useSearchParams();
  const editId = params.get("edit");
  const { data: draft, error: loadError } = useApi<StockRequestDetail>(editId ? `/stock-requests/${editId}` : null);
  if (editId && loadError) return <Alert>{loadError}</Alert>;
  if (editId && !draft) return <Loading />;
  return <RequestForm key={draft?.id ?? "new"} draft={draft} />;
}

function RequestForm({ draft }: { draft: StockRequestDetail | null }) {
  const router = useRouter();
  const { user } = useAuth();
  const isReseller = !!user?.reseller_id;
  const locations = useLocations(["CONSIGNMENT"]);
  const preset = Number(useSearchParams().get("location")) || "";       // ?location= from a dealer's page
  const [picked, setLocation] = useState<number | "">(draft?.location_id ?? preset);
  // A reseller with a single consignment location does not need to choose it.
  const location = picked !== "" ? picked : !draft && isReseller && locations?.length === 1 ? locations[0].id : "";
  const [rows, setRows] = useState<Row[]>(() => draft
    ? draft.lines.map((l) => ({ key: nextKey++, product: l.product_id, qty: String(l.qty_requested), notes: l.notes ?? "", findForMe: !!l.find_for_me }))
    : [blankRow()]);
  const [priority, setPriority] = useState(draft?.priority ?? "NORMAL");
  const [required, setRequired] = useState(draft?.required_date ?? "");
  const [notes, setNotes] = useState(draft?.notes ?? "");
  const [address, setAddress] = useState(draft?.shipping_address ?? "");
  const action = useAction();

  const update = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const filled = rows.filter((r) => r.product !== "" || r.qty !== "");
  const totalUnits = filled.reduce((a, r) => a + (Number(r.qty) || 0), 0);
  const dupes = new Set(filled.map((r) => r.product).filter((p, i, all) => p !== "" && all.indexOf(p) !== i));
  const invalid = !location || !filled.length || filled.some((r) => r.product === "" || !(Number(r.qty) > 0) || !Number.isInteger(Number(r.qty))) || dupes.size > 0;
  const priorities = isReseller ? ["HIGH", "NORMAL", "LOW"] : ["URGENT", "HIGH", "NORMAL", "LOW"];
  const needsHelp = useNeedsHelp(rows);

  async function save(submit: boolean) {
    const lines = filled.map((r) => ({ product_id: Number(r.product), quantity: Number(r.qty), notes: r.notes.trim() || null,
      find_for_me: r.findForMe && needsHelp.has(Number(r.product)) }));
    const body = { lines, priority, required_date: required || null, notes: notes.trim() || null, shipping_address: address.trim() || null };
    const res = await action.run(async () => {
      if (!draft) return api.post<StockRequestDetail>("/stock-requests", { ...body, location_id: location, submit });
      const saved = await api.put<StockRequestDetail>(`/stock-requests/${draft.id}`, body);
      return submit ? api.post<StockRequestDetail>(`/stock-requests/${draft.id}/submit`) : saved;
    });
    if (res) router.push(`/stock-requests/${res.id}`);
  }

  return (
    <>
      <PageHeader eyebrow="Consignment" title={draft ? `Edit ${draft.number}` : "Create stock request"}
        subtitle={isReseller
          ? `Ask for one or more ${vocab.items}. The Central Team reviews the request; stock is reserved for you once it is approved.`
          : `Request stock on behalf of ${vocab.aPartner}. You are recorded as the requester; the Central Team approves before stock is reserved.`}
        actions={!isReseller && <CheckStockButton />} />
      <Alert>{action.error}</Alert>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title={`${vocab.Items} requested`} className="xl:col-span-2" subtitle="One line per SKU. Quantities must be whole numbers greater than zero.">
          <div className="space-y-3">
            {rows.map((r, i) => (
              <div key={r.key} className="grid grid-cols-1 gap-2 rounded-control border border-line p-3 sm:grid-cols-[1fr_7rem_auto] sm:items-end">
                <Field label={`SKU ${i + 1}`} error={r.product !== "" && dupes.has(r.product) ? "This SKU is already on the request" : undefined}>
                  {(id) => <ProductSelect id={id} value={r.product} onChange={(p) => update(r.key, { product: p, findForMe: false })} />}
                </Field>
                <Field label="Quantity">
                  {(id) => <Input id={id} type="number" inputMode="numeric" min={1} step={1} value={r.qty} onChange={(e) => update(r.key, { qty: e.target.value })} />}
                </Field>
                <Button variant="ghost" aria-label={`Remove SKU ${i + 1}`} disabled={rows.length === 1}
                  onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}><Trash2 aria-hidden /></Button>
                {r.product !== "" && !dupes.has(r.product) && needsHelp.has(r.product) &&
                  <FindForMeNote chosen={r.findForMe} onChange={(v) => update(r.key, { findForMe: v })} />}
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button size="sm" onClick={() => setRows((rs) => [...rs, blankRow()])}><Plus aria-hidden />Add SKU</Button>
            <span className="ml-auto text-label text-ink-secondary"><b className="num text-ink">{filled.length}</b> SKU(s) · <b className="num text-ink">{totalUnits}</b> unit(s)</span>
          </div>
        </Card>

        <Card title="Request details">
          <div className="space-y-4">
            <Field label={isReseller ? "Deliver to" : `${vocab.Partner} location`} required
              hint={draft ? "The location cannot change on an existing request." : undefined}>
              {(id) => <LocationSelect id={id} types={["CONSIGNMENT"]} value={location} onChange={setLocation} disabled={!!draft} required />}
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Priority">
                {(id) => <Select id={id} value={priority} onChange={(e) => setPriority(e.target.value)} options={priorities.map((p) => ({ value: p, label: humanize(p) }))} />}
              </Field>
              <Field label="Required by">
                {(id) => <Input id={id} type="date" min={new Date().toISOString().slice(0, 10)} value={required} onChange={(e) => setRequired(e.target.value)} />}
              </Field>
            </div>
            <Field label="Shipping address" hint="Leave blank to use the location's address.">
              {(id) => <Textarea id={id} rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />}
            </Field>
            <Field label="Notes for the Central Team">
              {(id) => <Textarea id={id} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />}
            </Field>
            {user && <p className="text-caption text-ink-muted">Requested by <b className="font-medium text-ink-secondary">{user.full_name}</b> ({user.role_label})</p>}
            <div className="lg:border-t lg:border-line lg:pt-4">
              <MobileActionBar>
                <Button disabled={invalid || action.busy} onClick={() => save(false)}>Save draft</Button>
                <Button variant="primary" disabled={invalid || action.busy} onClick={() => save(true)}>
                  <Send aria-hidden />{action.busy ? "Submitting…" : "Submit for approval"}
                </Button>
              </MobileActionBar>
            </div>
          </div>
        </Card>
      </div>
      {!isReseller && filled.some((r) => r.product !== "") && (
        <div className="mt-4"><StockAvailability productIds={filled.filter((r) => r.product !== "").map((r) => Number(r.product))}
          dealerLocationId={location || null}
          requested={Object.fromEntries(filled.filter((r) => r.product !== "" && Number(r.qty) > 0).map((r) => [Number(r.product), Number(r.qty)]))} /></div>
      )}
    </>
  );
}
