"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { RefreshCw, Store, Truck } from "lucide-react";
import { FlowPath, Timeline, type Step } from "@/components/flow";
import { StockAvailability } from "@/components/StockAvailability";
import { blankReceipt, canConfirmCarried, PhotoPicker, ReceiptFields, receiptBody, receiptReady, ReceiptView, type Receipt } from "@/components/ReceiptProof";
import { ShippingMethodFields, shippingBody, shippingReady, TransferNoteActions, type Shipping } from "@/components/Shipping";
import {
  Alert, Badge, Button, Card, ConfirmDialog, DefinitionList, Field, Input, Loading, MobileActionBar, Modal, MoreMenu,
  type MoreMenuItem, PageHeader, Select, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Reseller, SourceOption, Transfer } from "@/lib/types";
import { vocab } from "@/lib/terms";

const blankShipping = (): Shipping => ({ method: "SALES_REP", carrier: "", repId: "" });

/** "Sales representative · Riley Rep" or "Courier · FastFreight · tracking FF1". */
function travelText(t: Transfer) {
  if (t.shipping_method === "SALES_REP") return `Sales representative · ${t.carried_by ?? ""}`;
  if (t.shipping_method === "COURIER") return `Courier · ${t.carrier_reference ?? "—"}${t.tracking_number ? ` · tracking ${t.tracking_number}` : ""}`;
  return null;
}

/** Body for POST /transfers/{id}/shipping (and the approve body's optional shipping block). */
function shippingIn(s: Shipping, tracking: string, route: Route) {
  return { ...shippingBody(s), carrier_reference: s.method === "COURIER" ? s.carrier.trim() : null,
    tracking_number: s.method === "COURIER" ? tracking.trim() || null : null, route };
}

type Route = "DIRECT" | "VIA_WAREHOUSE";
const viaWarehouse = (t: Transfer) => t.route === "VIA_WAREHOUSE";

/** Where the tyres go between the two dealers: chosen for each transfer (UAT round 2). */
function RouteChoice({ value, onChange }: { value: Route; onChange: (r: Route) => void }) {
  return (
    <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <legend className="mb-1.5 text-label font-medium text-ink">Route</legend>
      {([["DIRECT", `Direct to the ${vocab.partner}`, `Collected and taken straight to the receiving ${vocab.partner}.`],
        ["VIA_WAREHOUSE", "Via the warehouse", "Brought to the warehouse to be received and checked, then delivered."]] as const).map(([v, title, hint]) => (
        <label key={v} className={`flex cursor-pointer gap-2.5 rounded-control border p-3 ${value === v ? "border-ink bg-subtle" : "border-line"}`}>
          <input type="radio" name="route" className="mt-0.5 size-4 accent-ink" checked={value === v} onChange={() => onChange(v)} />
          <span><span className="block text-body font-medium">{title}</span><span className="block text-caption text-ink-muted">{hint}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

type Dialog = null | "approve" | "reject" | "cancel" | "collect" | "receive" | "resolve" | "shipping" | "warehouse";

export default function TransferDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can, user } = useAuth();
  const { data: t, error, setData } = useApi<Transfer>(`/transfers/${id}`);
  const [receipt, setReceipt] = useState<Receipt>(blankReceipt);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [qty, setQty] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [consent, setConsent] = useState("");
  const [outcome, setOutcome] = useState("RETURN_TO_SOURCE");
  const [ship, setShip] = useState<Shipping>(blankShipping);
  const [tracking, setTracking] = useState("");
  const [arrangeNow, setArrangeNow] = useState(false);
  const [collectedFrom, setCollectedFrom] = useState("");
  const [collectPhotos, setCollectPhotos] = useState<string[]>([]);
  const [route, setRoute] = useState<Route>("DIRECT");
  const [checkNotes, setCheckNotes] = useState("");
  const [checkPhotos, setCheckPhotos] = useState<string[]>([]);
  const action = useAction();
  const staffViewer = !!user && !user.reseller_id;
  // The destination dealer's rep is suggested to carry the tyres.
  const { data: destDealer } = useApi<Reseller>(staffViewer && t?.destination_reseller_id ? `/resellers/${t.destination_reseller_id}` : null);
  const shipping = ship.method === "SALES_REP" && ship.repId === "" && destDealer?.sales_rep_user_id ? { ...ship, repId: destDealer.sales_rep_user_id } : ship;
  const { data: sources } = useApi<{ warehouse_available: number; sources: SourceOption[] }>(
    dialog === "approve" && t ? "/transfers/sources" : null, { product_id: t?.product_id, exclude_location_id: t?.destination_location_id ?? undefined, quantity: t?.quantity });

  if (error) return <Alert>{error}</Alert>;
  if (!t) return <Loading />;

  const stopped = ["CANCELLED", "REJECTED"].includes(t.status);
  const raw = [
    { label: "Requested", done: true, at: t.requested_at, by: t.requested_by },
    { label: "Approved", done: !!t.approved_at, at: t.approved_at, by: t.approved_by, note: t.approved_at ? "Source stock reserved" : undefined },
    { label: "Pick-up arranged", done: !!t.shipping_arranged_at || !!t.collected_at, at: t.shipping_arranged_at, by: t.shipping_arranged_by,
      note: travelText(t) ?? undefined },
    { label: "Collected · in transit", done: !!t.collected_at, at: t.collected_at, by: t.collected_by,
      note: t.collected_from_name ? `Handed over by ${t.collected_from_name}` : undefined },
    ...(viaWarehouse(t) ? [{ label: "Received at the warehouse", done: !!t.warehouse_received_at, at: t.warehouse_received_at ?? undefined,
      by: t.warehouse_received_by ?? undefined, note: t.warehouse_check_notes ?? undefined }] : []),
    { label: "Received", done: !!t.received_at, at: t.received_at, by: t.received_by,
      note: t.status === "RECEIVED_WITH_DISCREPANCY" ? `${t.qty_in_transit} unit(s) not received` : undefined },
    { label: "Supplier replenished", done: t.source_request?.status === "FULFILLED" },
  ];
  const firstOpen = raw.findIndex((s) => !s.done);
  const steps: Step[] = raw.map((s, i) => ({ ...s,
    state: s.done ? (s.label === "Received" && t.status === "RECEIVED_WITH_DISCREPANCY" ? "failed" : "done") : i === firstOpen ? (stopped ? "failed" : "current") : "pending",
    label: !s.done && i === firstOpen && stopped ? `${humanize(t.status)}${t.cancel_reason ? `: ${t.cancel_reason}` : ""}` : s.label }));
  const selected = sources?.sources.find((s) => String(s.location_id) === sourceId);
  async function act(path: string, body: unknown) {
    const r = await action.run(() => api.post<Transfer>(`/transfers/${t!.id}/${path}`, body));
    if (r) { setData(r); setDialog(null); }
  }
  const open = (d: Dialog, q?: number) => {
    action.setError(null); setQty(q !== undefined ? String(q) : ""); setReceipt(blankReceipt()); setDialog(d);
    setShip(blankShipping()); setTracking(""); setArrangeNow(false); setCollectedFrom(""); setCollectPhotos([]);
    setRoute(t?.route ?? "DIRECT"); setCheckNotes(""); setCheckPhotos([]);
  };
  // The receiving dealer can confirm. A rep asked to carry it is the only staff member who can; for older transfers,
  // a Sales Rep who collected it.
  const carrierId = t.carried_by_user_id ?? (t.collected_by_sales_rep ? t.collected_by_user_id : null);
  const isReceiver = !!user?.reseller_id && user.reseller_id === t.destination_reseller_id;
  // Via the warehouse: it is delivered only after the warehouse has received and checked it.
  const awaitingCheck = t.status === "IN_TRANSIT" && viaWarehouse(t) && !t.warehouse_received_at;
  const mayCheck = awaitingCheck && can("transfer.approve");
  const mayReceive = !awaitingCheck && (isReceiver || can("transfer.execute")) && canConfirmCarried(user, carrierId);
  const isCarrier = !!user && carrierId === user.id;
  // With a rep assigned, only that rep (or an Administrator) records the collection.
  const mayCollect = can("transfer.execute") && (!t.carried_by_user_id || t.carried_by_user_id === user?.id || user?.role === "ADMINISTRATOR");
  const travel = travelText(t);

  // Phones and tablets in portrait: the next step in the bottom bar, the rest in "More". Who it is waiting for is the
  // header's status note at every size (first, where the desktop header always showed it).
  const next = t.status === "REQUESTED" && can("transfer.approve") ? <Button variant="primary" onClick={() => open("approve")}>Approve & choose source</Button>
    : t.status === "APPROVED" && mayCollect ? <Button variant="primary" onClick={() => open("collect", t.quantity)}>Record collection</Button>
    : mayCheck ? <Button variant="primary" onClick={() => open("warehouse")}>Received at the warehouse</Button>
    : t.status === "IN_TRANSIT" && mayReceive ? <Button variant="primary" onClick={() => open("receive", t.qty_in_transit)}>{isCarrier ? "Confirm delivery" : "Confirm receipt"}</Button>
    : null;
  const waiting = t.status === "APPROVED" && !mayCollect && t.carried_by && can("transfer.execute")
    ? <span className="self-center text-caption text-ink-muted">To be collected by {t.carried_by}</span>
    : awaitingCheck && !mayCheck
      ? <span className="self-center text-caption text-ink-muted">On its way to the warehouse to be checked</span>
    : t.status === "IN_TRANSIT" && !mayReceive && can("transfer.execute")
      ? <span className="self-center text-caption text-ink-muted">To be confirmed by the {vocab.partner} or {t.carried_by ?? t.collected_by}</span> : null;
  const more: MoreMenuItem[] = [
    ...(t.status === "REQUESTED" && can("transfer.approve") ? [{ label: "Reject transfer request", danger: true, onSelect: () => open("reject") }] : []),
    ...(["REQUESTED", "APPROVED"].includes(t.status) && can("transfer.approve") ? [{ label: "Cancel transfer", danger: true, onSelect: () => open("cancel") }] : []),
    ...(["IN_TRANSIT", "RECEIVED_WITH_DISCREPANCY"].includes(t.status) && can("transfer.approve")
      ? [{ label: t.status === "IN_TRANSIT" ? "Reverse / resolve" : "Resolve discrepancy", danger: true, onSelect: () => open("resolve", t.qty_in_transit) }] : []),
  ];

  return (
    <>
      <PageHeader status={waiting} mobileActions={<MoreMenu items={more} />} title={<span className="flex flex-wrap items-center gap-2">Transfer {t.number} <Badge value={t.status} /> <Badge value={t.urgency} /></span>}
        eyebrow="Stock transfer"
        subtitle={<>{t.quantity} × {t.product_name} <span className="sku text-label text-ink-secondary">{t.sku}</span></>}
        actions={<>
          {t.status === "REQUESTED" && can("transfer.approve") && <><Button variant="primary" onClick={() => open("approve")}>Approve & choose source</Button><Button onClick={() => open("reject")}>Reject</Button></>}
          {t.status === "APPROVED" && mayCollect && <Button variant="primary" onClick={() => open("collect", t.quantity)}>Record collection</Button>}
          {mayCheck && <Button variant="primary" onClick={() => open("warehouse")}>Received at the warehouse</Button>}
          {t.status === "IN_TRANSIT" && mayReceive && <Button variant="primary" onClick={() => open("receive", t.qty_in_transit)}>{isCarrier ? "Confirm delivery" : "Confirm receipt"}</Button>}
          {["REQUESTED", "APPROVED"].includes(t.status) && can("transfer.approve") && <Button variant="danger" onClick={() => open("cancel")}>Cancel</Button>}
          {["IN_TRANSIT", "RECEIVED_WITH_DISCREPANCY"].includes(t.status) && can("transfer.approve") && <Button variant="danger" onClick={() => open("resolve", t.qty_in_transit)}>{t.status === "IN_TRANSIT" ? "Reverse / resolve" : "Resolve discrepancy"}</Button>}
        </>} />
      <Alert>{action.error}</Alert>
      {t.status === "RECEIVED_WITH_DISCREPANCY" && <Alert tone="warn">{t.qty_in_transit} unit(s) were collected but not received. They remain visible in transit until resolved.</Alert>}

      {["REQUESTED", "APPROVED"].includes(t.status) && (
        <div className="mb-4"><StockAvailability productIds={[t.product_id]} dealerLocationId={t.destination_location_id}
          requested={{ [t.product_id]: t.quantity }} title="Stock for this transfer" /></div>
      )}
      <Card className="mb-4">
        <FlowPath
          from={{ eyebrow: `From · supplying ${vocab.partner}`, icon: Store, muted: !t.source_reseller_id,
            title: t.source_reseller_name ?? "Not yet selected", href: t.source_reseller_id ? `/resellers/${t.source_reseller_id}` : null,
            subtitle: t.source_location_code ?? "Chosen when the transfer is approved" }}
          to={{ eyebrow: `To · receiving ${vocab.partner}`, icon: Store, title: t.destination_reseller_name,
            href: t.destination_reseller_id ? `/resellers/${t.destination_reseller_id}` : null, subtitle: t.destination_location_code }}
          via={<>{t.quantity} × {t.product_name} <span className="sku text-label">{t.sku}</span>{t.qty_in_transit > 0 ? ` · ${t.qty_in_transit} in transit` : ""}</>}
          tone={t.status === "RECEIVED_WITH_DISCREPANCY" ? "danger" : t.status === "IN_TRANSIT" ? "accent" : "default"} />
        <div className="mt-6 border-t border-line pt-5"><Timeline steps={steps} /></div>
      </Card>

      {(t.status === "APPROVED" && can("transfer.approve")) || travel ? (
        <Card title="Pick-up & delivery" icon={Truck} className="mb-4"
          actions={t.status === "APPROVED" && can("transfer.approve") &&
            <Button size="sm" variant={travel ? "secondary" : "primary"} onClick={() => open("shipping")}>{travel ? "Change" : "Arrange pick-up & delivery"}</Button>}>
          {travel ? (
            <DefinitionList columns={2} items={[
              ["Travels with", travel], ["Arranged", t.shipping_arranged_at ? `${fmtDateTime(t.shipping_arranged_at)} · ${t.shipping_arranged_by ?? ""}` : null],
              ["Route", viaWarehouse(t) ? "Via the warehouse (received and checked there)" : `Direct to the ${vocab.partner}`],
              ["Collected from", t.collected_from_name],
              ...(viaWarehouse(t) ? [["Checked at the warehouse", t.warehouse_received_at
                ? `${fmtDateTime(t.warehouse_received_at)} · ${t.warehouse_received_by ?? ""}${t.warehouse_check_notes ? ` · ${t.warehouse_check_notes}` : ""}`
                : "Not yet"] as [string, string]] : []),
            ]} />
          ) : <p className="text-label text-ink-secondary">Say who collects the {vocab.items} from {t.source_reseller_name ?? `the supplying ${vocab.partner}`} and delivers them to {t.destination_reseller_name}: a sales representative (they are notified with both addresses) or a courier.</p>}
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Why and who" className="lg:col-span-2">
          <DefinitionList items={[
            ["Reason", t.reason], ["Requested by", t.requested_by], ["Approved by", t.approved_by], ["Approval notes", t.approval_notes],
            ["Source consent", t.source_consent_reference], ["Collected", t.qty_collected], ["Received", t.qty_received],
            ["Returned to source", t.qty_returned], ["Lost", t.qty_lost], ["Still in transit", t.qty_in_transit], ["Notes", t.notes],
            ["Invoicing", "None — a transfer is not a sale"],
          ]} />
          {t.received_at && <div className="mt-3 border-t border-line pt-3"><ReceiptView receivedBy={t.received_by_name} notes={t.receipt_notes} photos={t.photos} retired={t.photos_retired} />
            <div className="mt-3"><TransferNoteActions transfer={t} onChanged={() => api.get<Transfer>(`/transfers/${t.id}`).then(setData)} /></div></div>}
        </Card>
        <div className="space-y-4">
          <Card title="Replacement owed to supplier" icon={RefreshCw}>
            {t.source_request ? (
              <div>
                <div className="flex items-center justify-between gap-2"><Link className="link text-body-lg" href={`/replenishment/${t.source_request.id}`}>{t.source_request.number}</Link><Badge value={t.source_request.status} /></div>
                <p className="mt-2 text-label text-ink-secondary">{t.source_reseller_name} is owed replacement stock for what was collected.</p>
                <div className="mt-3 grid grid-cols-2 gap-3 rounded-control bg-subtle p-3 text-center">
                  <div><div className="num text-heading font-semibold">{t.source_request.qty_outstanding}</div><div className="text-caption text-ink-muted">Outstanding</div></div>
                  <div><div className="num text-heading font-semibold text-warning">{t.source_request.qty_awaiting_supply}</div><div className="text-caption text-ink-muted">Awaiting supply</div></div>
                </div>
              </div>
            ) : <p className="text-label text-ink-muted">Raised automatically when stock is collected from the source.</p>}
          </Card>
          {t.destination_request && (
            <Card title="Fulfils destination demand">
              <div className="flex items-center justify-between gap-2"><Link className="link" href={`/replenishment/${t.destination_request.id}`}>{t.destination_request.number}</Link><Badge value={t.destination_request.status} /></div>
            </Card>
          )}
        </div>
      </div>

      {next && <MobileActionBar desktop="hidden">{next}</MobileActionBar>}
      <ConfirmDialog open={dialog === "approve"} title="Approve transfer" busy={action.busy} error={action.error} confirmLabel="Approve & reserve"
        message={`Select the supplying ${vocab.partner}. Approval reserves the stock at the source.`} onClose={() => setDialog(null)}
        onConfirm={() => act("approve", { source_location_id: Number(sourceId), source_consent_reference: consent || null,
          ...(arrangeNow && shippingReady(shipping) ? { shipping: shippingIn(shipping, tracking, route) } : {}) })}>
        <Field label="Source location">{(fid) => <Select id={fid} value={sourceId} onChange={(e) => setSourceId(e.target.value)} placeholder="Select…"
          options={(sources?.sources ?? []).map((s) => ({ value: s.location_id, label: `${s.reseller_name} · ${s.location_code} · ${s.available} available${s.eligible ? "" : ` (${s.ineligible_reason})`}`, disabled: !s.eligible }))} />}</Field>
        {selected?.transfer_consent === "PER_TRANSFER" && <Field label="Source consent reference" required>{(fid) => <Input id={fid} value={consent} onChange={(e) => setConsent(e.target.value)} />}</Field>}
        <fieldset className="rounded-control border border-line p-3">
          <legend className="px-1 text-label font-medium text-ink">How will it travel? <span className="font-normal text-ink-muted">(optional)</span></legend>
          <label className="flex items-center gap-2 text-body">
            <input type="checkbox" className="size-4 accent-ink" checked={arrangeNow} onChange={(e) => setArrangeNow(e.target.checked)} />
            Arrange the pick-up now
          </label>
          {arrangeNow && <div className="mt-3 space-y-3"><ShippingMethodFields value={shipping} onChange={setShip} carrierLabel="Courier" />
            <RouteChoice value={route} onChange={setRoute} />
            {shipping.method === "COURIER" && <Field label="Tracking number">{(fid) => <Input id={fid} value={tracking} onChange={(e) => setTracking(e.target.value)} />}</Field>}</div>}
        </fieldset>
      </ConfirmDialog>
      <Modal open={dialog === "shipping"} title="Arrange pick-up & delivery" onClose={() => setDialog(null)}
        description={`Who collects ${t.quantity} × ${t.product_name} from ${t.source_reseller_name ?? `the supplying ${vocab.partner}`} and delivers to ${t.destination_reseller_name}.`}
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || !shippingReady(shipping)} onClick={() => act("shipping", shippingIn(shipping, tracking, route))}>
            {action.busy ? "Saving…" : "Save pick-up"}</Button></>}>
        <Alert>{action.error}</Alert>
        <ShippingMethodFields value={shipping} onChange={setShip} carrierLabel="Courier" />
        {shipping.method === "COURIER" && <Field label="Tracking number">{(fid) => <Input id={fid} value={tracking} onChange={(e) => setTracking(e.target.value)} />}</Field>}
        <RouteChoice value={route} onChange={setRoute} />
      </Modal>
      <Modal open={dialog === "warehouse"} title="Received at the warehouse" onClose={() => setDialog(null)}
        description={`${t.qty_in_transit} × ${t.product_name} collected from ${t.source_reseller_name ?? `the supplying ${vocab.partner}`}. Check them before ${t.carried_by ?? "the Sales Rep"} delivers to ${t.destination_reseller_name}. The stock stays in transit until it is delivered.`}
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || checkNotes.trim().length < 3}
            onClick={() => act("warehouse-receipt", { notes: checkNotes.trim(), photos: checkPhotos })}>{action.busy ? "Saving…" : "Received and checked"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label="What arrived and its condition" required hint="e.g. 3 arrived, good condition. Kept with the transfer.">
          {(fid) => <Textarea id={fid} rows={2} value={checkNotes} onChange={(e) => setCheckNotes(e.target.value)} />}
        </Field>
        <PhotoPicker photos={checkPhotos} onChange={setCheckPhotos} label="Photo at the warehouse" alt="Warehouse check photo" />
      </Modal>
      <ConfirmDialog open={dialog === "reject"} title="Reject transfer request" danger requireReason busy={action.busy} error={action.error} onClose={() => setDialog(null)} onConfirm={(reason) => act("reject", { reason })} />
      <ConfirmDialog open={dialog === "cancel"} title="Cancel transfer" danger requireReason busy={action.busy} error={action.error} onClose={() => setDialog(null)}
        message="Releases any reservation at the source. No replacement obligation exists before collection." onConfirm={(reason) => act("cancel", { reason })} />
      <Modal open={dialog === "collect"} title="Record collection from source" onClose={() => setDialog(null)}
        description={`Stock leaves ${t.source_location_code} and goes into transit. A replacement obligation to ${t.source_reseller_name} is raised for the collected quantity.`}
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || (!!t.carried_by_user_id && collectedFrom.trim().length < 2)}
            onClick={() => act("collect", { quantity: Number(qty), collected_from_name: collectedFrom.trim() || null, photos: collectPhotos })}>
            {action.busy ? "Saving…" : "Record collection"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label={`Quantity collected (max ${t.quantity})`}>{(fid) => <Input id={fid} type="number" min={1} max={t.quantity} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        <Field label="Collected from" required={!!t.carried_by_user_id} hint={`Name of the person at the ${vocab.partner} who handed the ${vocab.items} over.`}>
          {(fid) => <Input id={fid} value={collectedFrom} maxLength={120} placeholder="e.g. Sam (workshop manager)" onChange={(e) => setCollectedFrom(e.target.value)} />}
        </Field>
        <PhotoPicker photos={collectPhotos} onChange={setCollectPhotos} label="Photo at collection" alt="Collection photo" />
      </Modal>
      <Modal open={dialog === "receive"} title={isCarrier ? "Confirm delivery at destination" : "Confirm receipt at destination"} onClose={() => setDialog(null)}
        description="Enter what actually arrived. Any shortfall stays in transit as a discrepancy."
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || !receiptReady(receipt, user)}
            onClick={() => act("receive", { quantity: Number(qty), ...receiptBody(receipt) })}>{action.busy ? "Saving…" : "Confirm receipt"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label={`Quantity received (of ${t.qty_in_transit})`}>{(fid) => <Input id={fid} type="number" min={0} max={t.qty_in_transit} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        <ReceiptFields value={receipt} onChange={setReceipt} user={user} />
      </Modal>
      <ConfirmDialog open={dialog === "resolve"} title="Resolve in-transit quantity" danger requireReason busy={action.busy} error={action.error} onClose={() => setDialog(null)}
        onConfirm={(reason) => act("resolve", { outcome, quantity: Number(qty), reason })}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Outcome">{(fid) => <Select id={fid} value={outcome} onChange={(e) => setOutcome(e.target.value)} options={[
            { value: "RETURN_TO_SOURCE", label: "Return to source (reversal)" }, { value: "LATE_DELIVERY", label: "Arrived late at destination" },
            { value: "LOST", label: "Lost (write off — needs adjust permission)" }]} />}</Field>
          <Field label={`Quantity (max ${t.qty_in_transit})`}>{(fid) => <Input id={fid} type="number" min={1} max={t.qty_in_transit} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
        </div>
        <p className="text-caption text-ink-secondary">Returning stock reduces the supplier&apos;s replacement obligation. Lost stock keeps the obligation open.</p>
      </ConfirmDialog>
    </>
  );
}
