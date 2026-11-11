"use client";

import { Check, RefreshCw, Store } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckStockButton } from "@/components/CheckStock";
import { FlowPath } from "@/components/flow";
import { useMemo, useState } from "react";
import { LocationSelect, ProductSelect, useLocations, useProducts } from "@/components/pickers";
import {
  Alert, Badge, Button, Card, cx, DataTable, Field, Input, MobileActionBar, PageHeader, Select, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ReplenishmentRequest, SourceOption, Transfer } from "@/lib/types";

const STEPS = ["Requirement", "Availability & source", "Approval"];

/** Guided transfer: requesting reseller → SKU & qty → warehouse check → alternative sources → select → approve. */
export default function NewTransferPage() {
  const params = useSearchParams();
  const router = useRouter();
  const { can } = useAuth();
  const [step, setStep] = useState(0);
  const [dest, setDest] = useState<number | "">(params.get("destination") ? Number(params.get("destination")) : "");
  // "Cover with a transfer" on a backorder opens this form with the dealer, tyre, quantity and backorder filled in.
  const [product, setProduct] = useState<number | "">(params.get("product") ? Number(params.get("product")) : "");
  const [qty, setQty] = useState(params.get("qty") ?? "1");
  const [reason, setReason] = useState(params.get("reason") ?? "");
  const [urgency, setUrgency] = useState("URGENT");
  // null = not chosen: the receiving dealer's oldest open backorder for this tyre is linked by default, so the
  // backorder is covered (not supplied twice) and the giving dealer's replacement is tagged to it.
  const [destChoice, setDestRequest] = useState<string | null>(params.get("request"));
  const [source, setSource] = useState<SourceOption | null>(null);
  const [consent, setConsent] = useState("");
  const [notes, setNotes] = useState("");
  const action = useAction();
  const locations = useLocations(["CONSIGNMENT"]);
  const products = useProducts();
  const destLoc = locations?.find((l) => l.id === dest);
  const prod = products?.find((p) => p.id === product);

  const { data: sources } = useApi<{ warehouse_available: number; sources: SourceOption[] }>(
    step >= 1 && product ? "/transfers/sources" : null, { product_id: product, exclude_location_id: dest, quantity: qty });
  const { data: openReqs } = useApi<ReplenishmentRequest[]>(dest && product ? "/replenishment/requests" : null,
    { location_id: dest, product_id: product, backorders_only: true });
  const destBackorders = useMemo(() => (openReqs ?? []).filter((r) => r.qty_awaiting_supply > 0)
    .sort((a, b) => a.created_at.localeCompare(b.created_at)), [openReqs]);
  const destRequest = destChoice ?? (destBackorders[0] ? String(destBackorders[0].id) : "");
  const linkedReq = destBackorders.find((r) => String(r.id) === destRequest);
  const tooMany = !!linkedReq && Number(qty) > linkedReq.qty_awaiting_supply;
  const canApprove = can("transfer.approve");

  async function submit() {
    const t = await action.run(async () => {
      const created = await api.post<Transfer>("/transfers", {
        destination_location_id: dest, product_id: product, quantity: Number(qty), reason, urgency,
        destination_request_id: destRequest ? Number(destRequest) : null,
        notes: !canApprove && source ? `Suggested source: ${source.location_code} (${source.reseller_name}). ${notes}` : notes || null,
      });
      if (canApprove && source) {
        return api.post<Transfer>(`/transfers/${created.id}/approve`, {
          source_location_id: source.location_id, approval_notes: notes || null, source_consent_reference: consent || null,
        });
      }
      return created;
    });
    if (t) router.push(`/transfers/${t.id}`);
  }

  return (
    <>
      <PageHeader title="New inter-dealer transfer" subtitle="Use when the warehouse cannot supply an urgent need and another dealer holds unsold stock of the exact SKU."
        actions={can("transfer.request") && <CheckStockButton />} />
      <ol className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-body" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-3" aria-current={i === step ? "step" : undefined}>
            <span className="flex items-center gap-2">
              <span className={cx("inline-flex size-6 items-center justify-center rounded-full text-caption font-semibold",
                i === step ? "bg-brand text-ink" : i < step ? "bg-ink text-white" : "border border-line-strong text-ink-secondary")}>
                {i < step ? <Check className="size-3.5" strokeWidth={3} aria-hidden /> : i + 1}
              </span>
              <span className={i === step ? "font-medium text-ink" : "text-ink-secondary"}>{s}</span>
            </span>
            {i < STEPS.length - 1 && <span className="h-px w-8 bg-line-strong" aria-hidden />}
          </li>
        ))}
      </ol>
      <Alert>{action.error}</Alert>

      {step === 0 && (
        <Card title="Who needs what?" className="max-w-3xl">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Requesting (receiving) dealer location" required>{(id) => <LocationSelect id={id} types={["CONSIGNMENT"]} value={dest} onChange={(v) => { setDest(v); setDestRequest(null); }} />}</Field>
            <Field label="Quantity" required error={tooMany ? `${linkedReq?.number} has ${linkedReq?.qty_awaiting_supply} awaiting supply. Lower the quantity, or choose "No — separate urgent need" for the rest.` : undefined}>
              {(id, describedBy) => <Input id={id} type="number" min={1} value={qty} aria-invalid={tooMany || undefined} aria-describedby={describedBy} onChange={(e) => setQty(e.target.value)} />}</Field>
          </div>
          <div className="mt-3"><Field label="Exact SKU required" required hint="Only the exact SKU is searched; similar sizes are not substituted.">{(id) => <ProductSelect id={id} value={product} onChange={(v) => { setProduct(v); setDestRequest(null); }} />}</Field></div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Urgency">{(id) => <Select id={id} value={urgency} onChange={(e) => setUrgency(e.target.value)} options={["URGENT", "HIGH", "NORMAL"].map((u) => ({ value: u, label: humanize(u) }))} />}</Field>
            {destBackorders.length > 0 && (
              <Field label="Fulfils existing backorder?" hint="The oldest open backorder is linked, so it is not supplied twice and the giving dealer's replacement is tagged to it.">{(id) => <Select id={id} value={destRequest} onChange={(e) => setDestRequest(e.target.value)} placeholder="No — separate urgent need"
                options={destBackorders.map((r) => ({ value: r.id, label: `${r.number} · ${r.qty_awaiting_supply} awaiting (${humanize(r.reason)})` }))} />}</Field>
            )}
          </div>
          <div className="mt-3"><Field label="Reason" required>{(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. customer needs a matching pair today" />}</Field></div>
          <div className="mt-4"><MobileActionBar align="start"><Button variant="primary" disabled={!dest || !product || Number(qty) < 1 || tooMany || reason.trim().length < 3} onClick={() => setStep(1)}>Check availability</Button></MobileActionBar></div>
        </Card>
      )}

      {step === 1 && (
        <Card title={`Where can ${qty} × ${prod ? `${prod.display_name} (${prod.sku})` : ""} come from?`} padded={false}>
          <div className="p-4 pb-2">
            {sources && (sources.warehouse_available >= Number(qty)
              ? <Alert tone="warn">The warehouse has {sources.warehouse_available} available. Prefer normal replenishment unless the need is too urgent for a warehouse dispatch.</Alert>
              : <Alert tone="info">Warehouse available: {sources.warehouse_available}. Consignment locations holding available, unsold stock are listed below (reserved, blocked and sold stock are excluded).</Alert>)}
          </div>
          <DataTable mobile="cards" label="Supplying dealers" search={false} rows={sources?.sources} rowKey={(s) => s.location_id} empty="No other dealer holds this SKU."
            onRowClick={(s) => s.eligible && setSource(s)}
            columns={[
              { key: "sel", mobile: "status", header: "", cell: (s) => <label className="relative touch-target inline-flex size-5 items-center justify-center"><input type="radio" className="size-4 accent-ink" name="source" aria-label={`Select ${s.location_code}`} disabled={!s.eligible} checked={source?.location_id === s.location_id} onChange={() => setSource(s)} /></label> },
              { key: "r", mobile: "primary", header: "Supplying dealer", cell: (s) => <div><div className="font-medium">{s.reseller_name}</div><div className="text-label text-ink-secondary"><span className="sku">{s.account_ref}</span> · {s.location_code}</div></div> },
              { key: "oh", header: "On hand", align: "right", cell: (s) => s.on_hand },
              { key: "rs", header: "Reserved", align: "right", cell: (s) => s.reserved },
              { key: "bl", header: "Blocked", align: "right", cell: (s) => s.blocked },
              { key: "av", mobile: "field", mobileOrder: 1, header: "Available", align: "right", cell: (s) => <span className="font-semibold">{s.available}</span> },
              { key: "c", mobile: "field", mobileLabel: "Consent", mobileOrder: 2, header: "Consent rule", cell: (s) => humanize(s.transfer_consent) },
              { key: "e", mobile: "field", mobileOrder: 3, header: "Eligible", cell: (s) => s.eligible ? <Badge value="FULFILLED" label="Eligible" /> : <span className="text-caption text-danger">{s.ineligible_reason}</span> },
            ]} />
          <div className="lg:p-4">
            <MobileActionBar align="start">
              <Button onClick={() => setStep(0)}>Back</Button>
              <Button variant="primary" disabled={!source} onClick={() => setStep(2)}>Use {source?.location_code ?? "selected source"}</Button>
            </MobileActionBar>
          </div>
        </Card>
      )}

      {step === 2 && source && (
        <Card title="Confirm and approve" className="max-w-3xl">
          <FlowPath from={{ eyebrow: "From · supplying stock", icon: Store, title: source.reseller_name, subtitle: source.location_code }}
            to={{ eyebrow: "To · receiving stock", icon: Store, title: destLoc?.name, subtitle: destLoc?.code }}
            via={<>{qty} × {prod?.display_name} <span className="sku text-label">{prod?.sku}</span></>} tone="accent" />
          <div className="mt-3 flex items-start gap-3 rounded-control border border-warning-line bg-warning-soft p-3.5 text-label">
            <RefreshCw className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <div><div className="font-medium text-ink">Owed replacement</div><div className="text-ink-secondary">{source.reseller_name} is owed {qty} × {prod?.display_name} ({prod?.sku}), raised automatically on collection.</div></div>
          </div>
          <p className="mt-3 text-body text-ink-secondary">Approval reserves {qty} unit(s) at {source.location_code}. Neither dealer is invoiced for the transfer; {destLoc?.name ?? "the receiving dealer"} is invoiced only when it sells the tyres.</p>
          {canApprove ? (
            <div className="mt-3 space-y-3">
              {source.transfer_consent === "PER_TRANSFER" && <Field label="Source dealer consent reference" required hint="Their agreement requires consent for each transfer (who agreed, how, when).">{(id) => <Input id={id} value={consent} onChange={(e) => setConsent(e.target.value)} />}</Field>}
              <Field label="Approval notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
            </div>
          ) : (
            <Alert tone="info">You can raise the request; a dealership manager must approve it and confirm the source.</Alert>
          )}
          <div className="mt-4">
            <MobileActionBar align="start">
              <Button onClick={() => setStep(1)}>Back</Button>
              <Button variant="primary" disabled={action.busy || (canApprove && source.transfer_consent === "PER_TRANSFER" && !consent.trim())} onClick={submit}>
                {canApprove ? "Approve transfer & reserve stock" : "Submit transfer request"}
              </Button>
            </MobileActionBar>
          </div>
        </Card>
      )}
    </>
  );
}
