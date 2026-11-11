"use client";

import { ArrowLeftRight, CheckCheck, ClipboardCheck, PackageCheck, Pencil, Printer, Send, Truck, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { StockAvailability } from "@/components/StockAvailability";
import { CallMeButton } from "@/components/fulfilment/CallMeButton";
import { EscalateDialog, escalationText } from "@/components/fulfilment/EscalateDialog";
import { ApprovalFields, approvalBody, approvalLabel, approvalReady, blankApproval, type Approval } from "@/components/fulfilment/ApprovalDetails";
import { ConfirmDeliveryModal } from "@/components/fulfilment/ConfirmDeliveryModal";
import { ShipModal } from "@/components/fulfilment/ShipModal";
import { Timeline, type Step } from "@/components/flow";
import { NOT_AVAILABLE, roleLabel, StockRequestBadge, STATUS_LABEL, statusLabel } from "@/components/StockRequests";
import { ArrangingNote } from "@/components/FindForMe";
import { canConfirmCarried, ReceiptView } from "@/components/ReceiptProof";
import { DeliveryNoteActions } from "@/components/Shipping";
import { StockOrigin } from "@/components/StockOrigin";
import {
  Alert, Badge, Button, ButtonLink, Card, ConfirmDialog, cx, DataTable, DefinitionList, Field, Input, Loading,
  MetricStrip, MobileActionBar, Modal, MoreMenu, type MoreMenuItem, PageHeader, ProductCell, Qty, Select, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Delivery, StockRequestDetail, StockRequestLine, StockRequestStatus } from "@/lib/types";
import { TyreLabel } from "@/components/pickers";

const FULFILMENT: StockRequestStatus[] = ["APPROVED", "PARTIALLY_APPROVED", "READY_FOR_SHIPMENT", "SHIPPED", "DELIVERED"];
const ORDER: StockRequestStatus[] = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "READY_FOR_SHIPMENT", "SHIPPED", "DELIVERED"];

type Dialog =
  | null | "decide" | "reject" | "cancel" | "ship" | "escalate" | "handback"
  | { reserve: StockRequestLine } | { release: StockRequestLine } | { confirm: Delivery };

function steps(r: StockRequestDetail, dealer = false): Step[] {
  const ev = (...actions: string[]) => r.events.find((e) => actions.includes(e.action));
  const rank = ORDER.indexOf(["PARTIALLY_APPROVED", "REJECTED"].includes(r.status) ? "APPROVED" : r.status);
  const st = (i: number): Step["state"] => (rank > i ? "done" : rank === i ? "current" : "pending");
  const decided = ev("APPROVED", "PARTIALLY_APPROVED", "REJECTED");
  const shipped = ev("SHIPPED");
  const delivered = ev("DELIVERED");
  if (r.status === "CANCELLED") {
    const c = ev("CANCELLED");
    return [
      { label: "Created", state: "done", at: r.created_at, by: r.created_by },
      { label: "Cancelled", state: "failed", at: c?.occurred_at, by: c?.actor_name, note: c?.summary.replace(/^Cancelled: /, "") },
    ];
  }
  return [
    { label: "Draft", state: r.status === "DRAFT" ? "current" : "done", at: r.created_at, by: r.created_by },
    { label: "Submitted", state: st(1) === "current" ? "done" : st(1), at: r.submitted_at },
    { label: "Under review", state: r.decision ? "done" : st(2), at: ev("REVIEW_STARTED")?.occurred_at, by: ev("REVIEW_STARTED")?.actor_name },
    {
      label: r.decision ? statusLabel(r.decision, dealer) : "Approval", state: r.decision === "REJECTED" ? "failed" : r.decision ? "done" : "pending",
      at: decided?.occurred_at, by: decided ? `${decided.actor_name} · ${roleLabel(decided.actor_role)}` : null,
    },
    ...(r.decision === "REJECTED" ? [] : [
      { label: "Ready for shipment", state: r.ready_at || rank > 4 ? "done" as const : "pending" as const, at: ev("READY_FOR_SHIPMENT")?.occurred_at },
      { label: "Shipped", state: r.status === "SHIPPED" ? "current" as const : shipped ? "done" as const : "pending" as const, at: shipped?.occurred_at, by: shipped?.actor_name },
      { label: "Delivered", state: r.status === "DELIVERED" ? "done" as const : "pending" as const, at: delivered?.occurred_at, by: delivered?.actor_name },
    ]),
  ];
}

export default function StockRequestPage() {
  const { id } = useParams<{ id: string }>();
  const { user, can } = useAuth();
  const { data: r, error, setData } = useApi<StockRequestDetail>(`/stock-requests/${id}`);
  const [dialog, setDialog] = useState<Dialog>(null);
  const action = useAction();

  if (error) return <Alert>{error}</Alert>;
  if (!r || !user) return <Loading />;

  const approver = can("stock_request.approve");
  const fulfiller = can("stock_request.fulfil");
  const canChange = user.id === r.created_by_user_id || approver || (user.reseller_id !== null && user.reseller_id === r.reseller_id);
  const pending = r.status === "SUBMITTED" || r.status === "UNDER_REVIEW";
  // While it waits for a Relationship Manager, only they (or an Administrator) decide it (D10).
  const escalated = pending && !!r.escalated_to_user_id;
  const mayDecide = approver && (!escalated || user.id === r.escalated_to_user_id || user.role === "ADMINISTRATOR");
  const inFulfilment = FULFILMENT.includes(r.status);
  const staff = !user.reseller_id;

  async function act(path: string, body: unknown = {}) {
    const res = await action.run(() => api.post<StockRequestDetail>(`/stock-requests/${r!.id}${path}`, body));
    if (res) { setData(res); setDialog(null); }
    return res;
  }

  // Phones and tablets in portrait: the one next action sits in the bottom bar, the rest in "More" (same order as the
  // desktop header, destructive ones last).
  const showPrint = staff && ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PARTIALLY_APPROVED", "READY_FOR_SHIPMENT"].includes(r.status);
  const shipping = inFulfilment && fulfiller && r.qty_reserved > 0;
  const confirmable = r.shipments.filter((d) => d.status === "IN_TRANSIT" && can("delivery.confirm")
    && canConfirmCarried(user, d.shipping_method === "SALES_REP" ? d.carried_by_user_id : null));
  const next = r.status === "DRAFT" && canChange
    ? <Button variant="primary" disabled={action.busy} onClick={() => act("/submit")}><Send aria-hidden />Submit for approval</Button>
    : pending && mayDecide ? <Button variant="primary" onClick={() => setDialog("decide")}><CheckCheck aria-hidden />Approve…</Button>
    : shipping ? <Button variant="primary" onClick={() => setDialog("ship")}><Truck aria-hidden />Ship</Button>
    : confirmable.length === 1 ? <Button variant="primary" onClick={() => setDialog({ confirm: confirmable[0] })}>Confirm delivery</Button>
    : null;
  const confirmInBar = !!next && r.status !== "DRAFT" && !(pending && mayDecide) && !shipping;
  const more: MoreMenuItem[] = [
    ...(showPrint ? [{ label: "Print pick sheet", href: `/stock-requests/${r.id}/print`, icon: Printer }] : []),
    ...(r.status === "DRAFT" && canChange ? [{ label: "Edit", href: `/stock-requests/new?edit=${r.id}`, icon: Pencil }] : []),
    ...(r.status === "SUBMITTED" && approver ? [{ label: "Start review", icon: ClipboardCheck, disabled: action.busy, onSelect: () => act("/review") }] : []),
    ...(pending && approver && !escalated && user.role === "WAREHOUSE_MANAGER" ? [{ label: "Send to Relationship Manager", icon: Send, onSelect: () => setDialog("escalate") }] : []),
    ...(escalated && mayDecide ? [{ label: "Hand back to warehouse", onSelect: () => setDialog("handback") }] : []),
    ...(shipping && !r.ready_at && r.status !== "SHIPPED" ? [{ label: "Mark ready for shipment", icon: PackageCheck, disabled: action.busy, onSelect: () => act("/ready") }] : []),
    ...(pending && mayDecide ? [{ label: "Reject request", icon: X, danger: true, onSelect: () => setDialog("reject") }] : []),
    ...((r.status === "DRAFT" || pending) && canChange ? [{ label: "Cancel request", danger: true, onSelect: () => setDialog("cancel") }] : []),
  ];

  return (
    <>
      <PageHeader eyebrow="Consignment stock request" mobileActions={<MoreMenu items={more} />}
        title={<span className="flex flex-wrap items-center gap-2">{r.number} <StockRequestBadge status={r.status} /> <Badge value={r.priority} /></span>}
        subtitle={<>{r.qty_requested} unit(s) across {r.line_count} SKU(s) for {staff ? <Link className="link" href={`/resellers/${r.reseller_id}`}>{r.reseller_name}</Link> : r.reseller_name} ({r.location_code})</>}
        actions={<>
          {staff && ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PARTIALLY_APPROVED", "READY_FOR_SHIPMENT"].includes(r.status) &&
            <ButtonLink href={`/stock-requests/${r.id}/print`}><Printer aria-hidden />Print pick sheet</ButtonLink>}
          {r.status === "DRAFT" && canChange && <>
            <ButtonLink href={`/stock-requests/new?edit=${r.id}`}><Pencil aria-hidden />Edit</ButtonLink>
            <Button variant="primary" disabled={action.busy} onClick={() => act("/submit")}><Send aria-hidden />Submit for approval</Button>
          </>}
          {r.status === "SUBMITTED" && approver && <Button disabled={action.busy} onClick={() => act("/review")}><ClipboardCheck aria-hidden />Start review</Button>}
          {pending && approver && !escalated && user.role === "WAREHOUSE_MANAGER" &&
            <Button onClick={() => setDialog("escalate")}><Send aria-hidden />Send to Relationship Manager</Button>}
          {escalated && mayDecide && <Button onClick={() => setDialog("handback")}>Hand back to warehouse</Button>}
          {pending && mayDecide && <>
            <Button variant="danger" onClick={() => setDialog("reject")}><X aria-hidden />Reject</Button>
            <Button variant="primary" onClick={() => setDialog("decide")}><CheckCheck aria-hidden />Approve…</Button>
          </>}
          {(r.status === "DRAFT" || pending) && canChange && <Button variant="ghost" onClick={() => setDialog("cancel")}>Cancel request</Button>}
          {inFulfilment && fulfiller && r.qty_reserved > 0 && <>
            {!r.ready_at && r.status !== "SHIPPED" && <Button disabled={action.busy} onClick={() => act("/ready")}><PackageCheck aria-hidden />Mark ready for shipment</Button>}
            <Button variant="primary" onClick={() => setDialog("ship")}><Truck aria-hidden />Ship</Button>
          </>}
        </>} />
      <Alert>{dialog === null ? action.error : null}</Alert>

      {staff && escalated && <Alert tone="warn">{escalationText(r)}</Alert>}
      {!staff && r.decision && r.qty_rejected > 0 && (
        <Alert tone="info">
          <div className="flex flex-wrap items-center justify-between gap-3"><span>{r.review_notes}</span>
            <CallMeButton requestId={r.id} number={r.number} /></div>
        </Alert>
      )}
      <Card className="mb-4"><Timeline steps={steps(r, !staff)} /></Card>
      {staff && r.approval_method && (
        <Card title="Approval" className="mb-4">
          <DefinitionList columns={2} items={[
            ["Approved by", `${r.reviewed_by ?? "—"}${r.reviewed_by_role ? ` · ${roleLabel(r.reviewed_by_role)}` : ""}`],
            ["How", approvalLabel(r.approval_method)], ["Spoke to", r.approval_contact ?? "—"], ["Comments", r.approval_comments],
          ]} />
        </Card>
      )}

      <MetricStrip items={[
        { label: "Requested", value: r.qty_requested },
        { label: "Approved", value: r.decision ? r.qty_approved : "—", tone: "accent" },
        { label: "Backordered", value: r.decision ? r.qty_backordered : "—", tone: r.qty_backordered ? "warn" : "default" },
        { label: staff ? "Rejected" : NOT_AVAILABLE, value: r.decision ? r.qty_rejected : "—" },
        { label: "Reserved, to ship", value: r.qty_reserved, tone: r.qty_reserved ? "info" : "default" },
        { label: "Shipped", value: r.qty_shipped },
        { label: "Delivered", value: r.qty_delivered, tone: r.qty_delivered ? "ok" : "default" },
      ]} className="lg:grid-cols-7" />

      {staff && <div className="mb-4"><StockAvailability productIds={r.lines.map((l) => l.product_id)} dealerLocationId={r.location_id}
        requested={Object.fromEntries(r.lines.map((l) => [l.product_id, l.qty_requested]))} /></div>}

      <Card title="Lines" padded={false} className="mb-4">
        <DataTable mobile="cards" label="Requested tyres" search={false} rows={r.lines} rowKey={(l) => l.id} columns={[
          { key: "p", mobile: "primary" as const, header: "SKU", className: "min-w-56 whitespace-normal", cell: (l) => (
            <div>
              <div className="flex items-center gap-1"><ProductCell sku={l.sku} name={l.product_name} /><StockOrigin locationId={r.location_id} productId={l.product_id} /></div>
              {!l.product_active && <Badge value="CLOSED" label="Inactive SKU" />}
              {l.first_supply && <Badge value="LATEST_STOCK" label="Latest stock" />}
              {l.notes && <div className="mt-0.5 text-caption text-ink-muted">{l.notes}</div>}
              {l.decision_notes && <div className="mt-0.5 text-caption text-ink-secondary">Decision: {l.decision_notes}</div>}
              {!!l.qty_arranging && (staff
                ? <div className="mt-0.5 text-caption text-ink-secondary">Being arranged from another dealer: <b className="num">{l.qty_arranging}</b>
                    {l.arranging_transfer_id && <> · <Link className="link" href={`/transfers/${l.arranging_transfer_id}`}>{l.arranging_transfer_number}</Link></>}</div>
                : <ArrangingNote />)}
              {staff && (l.covering_transfers ?? []).map((t) => (
                <div key={t.id} className="mt-0.5 text-caption text-ink-secondary">Arranged from another dealer: <b className="num">{t.quantity}</b> ·{" "}
                  <Link className="link" href={`/transfers/${t.id}`}>{t.number}</Link> <Badge value={t.status} /></div>
              ))}
              {staff && can("transfer.request") && l.qty_backorder_open > 0 && l.replenishment_request_id
                && !(l.covering_transfers ?? []).some((t) => ["REQUESTED", "APPROVED", "IN_TRANSIT"].includes(t.status)) && (
                <ButtonLink size="sm" variant="ghost" className="mt-1" href={`/transfers/new?${new URLSearchParams({ destination: String(r.location_id),
                  product: String(l.product_id), qty: String(l.qty_backorder_open), request: String(l.replenishment_request_id),
                  reason: `Rest of ${r.number}: arranged from another dealer` })}`}>
                  <ArrowLeftRight aria-hidden />Cover with a transfer<span className="sr-only"> for {l.sku}</span></ButtonLink>
              )}
            </div>
          ) },
          { key: "q", mobile: "field" as const, mobileOrder: 1, header: "Requested", align: "right", cell: (l) => <span className="num font-medium">{l.qty_requested}</span> },
          { key: "a", mobile: "field" as const, mobileOrder: 2, header: "Approved", align: "right", cell: (l) => r.decision ? <Qty value={l.qty_approved} zeroMuted={false} /> : "—" },
          { key: "rj", header: staff ? "Rejected" : NOT_AVAILABLE, align: "right", cell: (l) => r.decision ? <Qty value={l.qty_rejected} /> : "—" },
          { key: "b", header: "Backordered", align: "right", cell: (l) => r.decision ? (
            <span title={`${l.qty_backorder_open} still awaiting supply`}><Qty value={l.qty_backordered} tone="warn" /></span>
          ) : "—" },
          { key: "rs", header: "Reserved", align: "right", cell: (l) => <Qty value={l.qty_reserved} /> },
          { key: "sh", mobile: "field" as const, mobileOrder: 3, header: "Shipped", align: "right", cell: (l) => <Qty value={l.qty_shipped} /> },
          { key: "dl", mobile: "field" as const, mobileOrder: 4, header: "Delivered", align: "right", cell: (l) => <Qty value={l.qty_delivered} tone="ok" /> },
          ...(staff ? [{ key: "av", header: "Warehouse available", align: "right" as const, cell: (l: StockRequestLine) => (
            <Qty value={l.warehouse_available} zeroMuted={false} tone={l.warehouse_available === 0 ? "danger" : undefined} />
          ) }] : []),
          ...(approver && inFulfilment ? [{ key: "x", mobile: "action" as const, header: <span className="sr-only">Actions</span>, cell: (l: StockRequestLine) => (
            <div className="flex justify-end gap-1">
              {l.qty_backorder_open > 0 && l.qty_backordered > 0 && (l.warehouse_available ?? 0) > 0 &&
                <Button size="sm" variant="ghost" onClick={() => setDialog({ reserve: l })}>Reserve</Button>}
              {l.qty_reserved > 0 && <Button size="sm" variant="ghost" onClick={() => setDialog({ release: l })}>Release</Button>}
            </div>
          ) }] : []),
        ]} />
      </Card>

      {r.shipments.length > 0 && (
        <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
          {r.shipments.map((d) => (
            <Card key={d.id} title={<span className="flex items-center gap-2">Shipment {d.number} <Badge value={d.status} /></span>}
              actions={d.status === "IN_TRANSIT" && can("delivery.confirm") && (canConfirmCarried(user, d.shipping_method === "SALES_REP" ? d.carried_by_user_id : null)
                ? <Button size="sm" variant="primary" className={cx(confirmInBar && "max-lg:hidden")} onClick={() => setDialog({ confirm: d })}>Confirm delivery</Button>
                : <span className="text-caption text-ink-muted">To be confirmed by the dealer or {d.carried_by}</span>)}>
              <DefinitionList columns={1} items={[
                ["Shipped with", d.shipping_method === "SALES_REP" ? `Sales representative · ${d.carried_by ?? ""}` : `Courier · ${d.carrier_reference ?? "—"}`],
                ["Tracking number", d.tracking_number], ["Ship to", d.shipping_address],
                ["Shipped", `${fmtDateTime(d.dispatched_at)} · ${d.dispatched_by ?? ""}`], ["Shipment notes", d.notes],
                ...(d.received_at ? [
                  ["Delivered on", `${fmtDate(d.delivered_on)} · confirmed by ${d.received_by ?? ""}`],
                  ["Delivery reference", d.delivery_reference],
                ] as [string, string | null | undefined][] : []),
              ]} />
              {d.received_at && <div className="mt-2"><ReceiptView receivedBy={d.received_by_name} notes={d.receipt_notes} photos={d.photos} retired={d.photos_retired} /></div>}
              <div className="mt-3"><DeliveryNoteActions delivery={d} onChanged={() => api.get<StockRequestDetail>(`/stock-requests/${r.id}`).then(setData)} /></div>
              <ul className="mt-3 divide-y divide-line rounded-control border border-line text-label">
                {d.lines.map((ln) => (
                  <li key={ln.id} className="flex items-center gap-3 px-3 py-2">
                    <TyreLabel sku={ln.sku} productId={ln.product_id} />
                    <span className="ml-auto text-ink-secondary">shipped <b className="num text-ink">{ln.qty_dispatched}</b></span>
                    {d.status !== "IN_TRANSIT" && <span className="text-ink-secondary">received <b className="num text-ink">{ln.qty_received + ln.qty_late_received}</b></span>}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Details">
          <DefinitionList columns={1} items={[
            ["Requested by", <>{r.created_by} <span className="text-ink-muted">· {roleLabel(r.created_by_role)}</span></>],
            ["Created", fmtDateTime(r.created_at)], ["Submitted", fmtDateTime(r.submitted_at)],
            ["Required by", fmtDate(r.required_date)], ["Ship to", r.shipping_address], ["Notes", r.notes],
            ["Reviewed by", r.reviewed_by ? <>{r.reviewed_by} <span className="text-ink-muted">· {roleLabel(r.reviewed_by_role)}</span></> : null],
            ["Reviewed", fmtDateTime(r.reviewed_at)], ["Review notes", r.review_notes],
            ...(staff ? [["Replenishment lines", r.lines.filter((l) => l.replenishment_request_id).map((l) => (
              <Link key={l.id} className="link mr-2" href={`/replenishment/${l.replenishment_request_id}`}>{l.replenishment_number}</Link>
            ))] as [string, ReactNode]] : []),
          ]} />
        </Card>
        <Card title="History" subtitle="Every action with the user, role, quantities and status" padded={false}>
          <ol className="divide-y divide-line">
            {[...r.events].reverse().map((e) => (
              <li key={e.id} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label">
                  <span className="font-medium text-ink">{e.actor_name ?? "System"}</span>
                  {e.actor_role && <span className="text-ink-muted">{roleLabel(e.actor_role)}</span>}
                  {e.to_status && e.from_status !== e.to_status && <StockRequestBadge status={e.to_status as StockRequestStatus} />}
                  <time className="ml-auto text-caption text-ink-muted">{fmtDateTime(e.occurred_at)}</time>
                </div>
                <p className="mt-0.5 text-label text-ink-secondary">{e.summary}</p>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      {next && <MobileActionBar desktop="hidden">{next}</MobileActionBar>}

      {dialog === "decide" && <DecisionModal r={r} busy={action.busy} error={action.error} onClose={() => { setDialog(null); action.setError(null); }}
        onSubmit={(body) => act("/decision", body)} />}
      {dialog === "ship" && <ShipModal number={r.number} resellerId={r.reseller_id} address={r.shipping_address}
        lines={r.lines.filter((l) => l.qty_reserved > 0).map((l) => ({ key: l.id, sku: l.sku, productName: l.product_name, reserved: l.qty_reserved }))}
        busy={action.busy} error={action.error} onClose={() => { setDialog(null); action.setError(null); }}
        onSubmit={(x) => act("/ship", {
          ...x.shipping, carrier: x.carrier, tracking_number: x.tracking_number, shipping_address: x.shipping_address, notes: x.notes,
          lines: x.quantities.map((q) => ({ line_id: q.key, quantity: q.quantity })),
        })} />}
      {typeof dialog === "object" && dialog && "confirm" in dialog && <ConfirmDeliveryModal d={dialog.confirm} busy={action.busy} error={action.error}
        onClose={() => { setDialog(null); action.setError(null); }} onSubmit={(body) => act(`/shipments/${dialog.confirm.id}/confirm`, body)} />}
      {dialog === "escalate" && <EscalateDialog number={r.number} busy={action.busy} error={action.error}
        onClose={() => { setDialog(null); action.setError(null); }} onSubmit={(body) => act("/escalate", body)} />}
      <ConfirmDialog open={dialog === "handback"} title="Hand back to the warehouse" busy={action.busy} error={action.error} confirmLabel="Hand back"
        message="The warehouse can decide this request again." onClose={() => { setDialog(null); action.setError(null); }}
        onConfirm={() => act("/hand-back", { note: null })} />
      <ConfirmDialog open={dialog === "reject"} title={`Reject ${r.number}`} danger requireReason busy={action.busy} error={action.error}
        confirmLabel="Reject request" message="Nothing is reserved. The requester and the dealer are notified with your reason."
        onClose={() => { setDialog(null); action.setError(null); }} onConfirm={(reason) => act("/reject", { reason })} />
      <ConfirmDialog open={dialog === "cancel"} title={`Cancel ${r.number}`} requireReason busy={action.busy} error={action.error}
        confirmLabel="Cancel request" message="The request is withdrawn before any decision. It stays in the history."
        onClose={() => { setDialog(null); action.setError(null); }} onConfirm={(reason) => act("/cancel", { reason })} />
      {typeof dialog === "object" && dialog && "reserve" in dialog && <ReserveDialog line={dialog.reserve} busy={action.busy} error={action.error}
        onClose={() => { setDialog(null); action.setError(null); }} onSubmit={(qty) => act(`/lines/${dialog.reserve.id}/reserve`, { quantity: qty })} />}
      {typeof dialog === "object" && dialog && "release" in dialog && <ReleaseDialog line={dialog.release} busy={action.busy} error={action.error}
        onClose={() => { setDialog(null); action.setError(null); }} onSubmit={(body) => act(`/lines/${dialog.release.id}/release`, body)} />}
    </>
  );
}

interface ModalProps<B> { busy: boolean; error: string | null; onClose: () => void; onSubmit: (body: B) => void }

function DecisionModal({ r, busy, error, onClose, onSubmit }: ModalProps<unknown> & { r: StockRequestDetail }) {
  // Quantity being arranged from another dealer ("Get this tyre for me") is not part of this decision.
  const toDecide = (l: StockRequestLine) => l.qty_requested - (l.qty_arranging ?? 0);
  const arranging = r.lines.reduce((a, l) => a + (l.qty_arranging ?? 0), 0);
  const [rows, setRows] = useState(() => r.lines.map((l) => ({
    line_id: l.id, approve: String(l.product_active ? Math.min(toDecide(l), Math.max(0, l.warehouse_available ?? 0)) : 0),
    remainder: l.product_active ? "BACKORDER" : "REJECT", notes: "",
  })));
  const [notes, setNotes] = useState("");
  const [step, setStep] = useState<"quantities" | "approval">("quantities");
  const [approval, setApproval] = useState<Approval>(blankApproval);
  const set = (i: number, patch: Partial<(typeof rows)[number]>) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const parsed = rows.map((x, i) => ({ ...x, qty: Number(x.approve), line: r.lines[i] }));
  const invalid = parsed.some((x) => !Number.isInteger(x.qty) || x.qty < 0 || x.qty > toDecide(x.line) || x.qty > (x.line.warehouse_available ?? 0));
  const approved = parsed.reduce((a, x) => a + (x.qty || 0), 0);
  // "Arrange from another dealer" is a backorder with a transfer request raised for it straight away.
  const backordered = parsed.reduce((a, x) => a + (x.remainder !== "REJECT" ? toDecide(x.line) - (x.qty || 0) : 0), 0);
  const toArrange = parsed.reduce((a, x) => a + (x.remainder === "TRANSFER" ? toDecide(x.line) - (x.qty || 0) : 0), 0);
  const rejected = r.qty_requested - arranging - approved - backordered;
  const outcome = approved === 0 && backordered === 0 && arranging === 0 ? "REJECTED"
    : approved + arranging === r.qty_requested ? "APPROVED" : "PARTIALLY_APPROVED";
  const needsApproval = approved + backordered > 0;
  const submit = () => onSubmit({ notes: notes.trim() || null, ...(needsApproval ? { approval: approvalBody(approval) } : {}),
    lines: parsed.map((x) => ({ line_id: x.line_id, approve_qty: x.qty, remainder: x.remainder, notes: x.notes.trim() || null })) });
  const verb = outcome === "APPROVED" ? "Approve and reserve" : outcome === "REJECTED" ? "Reject request" : "Partially approve";

  if (step === "approval") {
    return (
      <Modal open title="Approval details" description={`${verb}: ${approved} approved and reserved, ${backordered} backordered${toArrange ? ` (${toArrange} to arrange from another dealer)` : ""}, ${rejected} rejected.`} onClose={onClose}
        footer={<>
          <Button onClick={() => setStep("quantities")}>Back</Button>
          <Button variant="primary" disabled={busy || !approvalReady(approval)} onClick={submit}>{busy ? "Saving…" : "Confirm approval"}</Button>
        </>}>
        <Alert>{error}</Alert>
        <ApprovalFields value={approval} onChange={setApproval} />
      </Modal>
    );
  }

  return (
    <Modal open wide title={`Review ${r.number}`} onClose={onClose}
      description="Approve what the warehouse can supply now; it is reserved immediately. For the rest of each line choose backorder (reserved when stock arrives) or reject."
      footer={<>
        <Button onClick={onClose}>Back</Button>
        <Button variant={outcome === "REJECTED" ? "danger" : "primary"} disabled={busy || invalid}
          onClick={() => (needsApproval ? setStep("approval") : submit())}>
          {busy ? "Saving…" : verb}
        </Button>
      </>}>
      <Alert>{error}</Alert>
      <div className="overflow-x-auto rounded-control border border-line">
        <table className="w-full text-label">
          <thead className="bg-subtle text-left text-caption text-ink-muted">
            <tr><th className="px-3 py-2 font-medium">SKU</th><th className="px-3 py-2 text-right font-medium">Requested</th>
              <th className="px-3 py-2 text-right font-medium">Available</th>
              <th className="px-3 py-2 text-right font-medium">Dealer already holds</th><th className="px-3 py-2 font-medium">Approve</th>
              <th className="px-3 py-2 font-medium">Remainder</th><th className="px-3 py-2 font-medium">Note</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {parsed.map((x, i) => {
              const rest = toDecide(x.line) - (x.qty || 0);
              const over = x.qty > (x.line.warehouse_available ?? 0);
              return (
                <tr key={x.line_id}>
                  <td className="px-3 py-2"><ProductCell sku={x.line.sku} name={x.line.product_name} />
                    {!!x.line.qty_arranging && <div className="text-caption text-ink-muted">{x.line.qty_arranging} being arranged from another dealer</div>}</td>
                  <td className="num px-3 py-2 text-right font-medium">{x.line.qty_requested}</td>
                  <td className="px-3 py-2 text-right"><Qty value={x.line.warehouse_available} zeroMuted={false} tone={x.line.warehouse_available ? undefined : "danger"} /></td>
                  <td className="px-3 py-2 text-right" title={x.line.dealer_on_hand_all != null ? `All of this dealer's shops: ${x.line.dealer_on_hand_all}` : undefined}>
                    <Qty value={x.line.dealer_on_hand ?? null} />
                    {(x.line.dealer_on_hand ?? 0) >= x.line.qty_requested && x.line.qty_requested > 0 &&
                      <div className="mt-1 max-w-48 text-left text-caption text-warning" role="note">This dealer already holds {x.line.dealer_on_hand} of this tyre. Check with them before approving?</div>}
                  </td>
                  <td className="w-28 px-3 py-2">
                    <Input aria-label={`Approve quantity for ${x.line.sku}`} aria-invalid={over || x.qty > toDecide(x.line)} type="number" min={0}
                      max={Math.min(toDecide(x.line), x.line.warehouse_available ?? 0)} value={x.approve} disabled={!x.line.product_active}
                      onChange={(e) => set(i, { approve: e.target.value })} />
                    {over && <div className="mt-1 text-caption text-danger">Only {x.line.warehouse_available} available</div>}
                  </td>
                  <td className="w-40 px-3 py-2">
                    {rest > 0 ? (
                      <Select aria-label={`Remainder for ${x.line.sku}`} value={x.remainder} onChange={(e) => set(i, { remainder: e.target.value })}
                        options={[...(x.line.product_active ? [{ value: "BACKORDER", label: `Backorder ${rest}` },
                          { value: "TRANSFER", label: `Arrange ${rest} from another dealer` }] : []), { value: "REJECT", label: `Reject ${rest}` }]} />
                    ) : <span className="text-ink-muted">—</span>}
                  </td>
                  <td className="px-3 py-2"><Input aria-label={`Decision note for ${x.line.sku}`} value={x.notes} onChange={(e) => set(i, { notes: e.target.value })} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 rounded-control border border-line px-4 py-3 text-label">
        <span>Outcome: <b>{STATUS_LABEL[outcome as StockRequestStatus]}</b></span>
        <span><b className="num">{approved}</b> approved & reserved</span>
        <span><b className="num">{backordered}</b> backordered</span>
        <span><b className="num">{rejected}</b> rejected</span>
        {arranging > 0 && <span><b className="num">{arranging}</b> being arranged by the warehouse</span>}
      </div>
      <Field label="Decision notes" hint="Shared with the requester and recorded in the audit trail.">
        {(fid) => <Textarea id={fid} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}
      </Field>
    </Modal>
  );
}

function ReserveDialog({ line, busy, error, onClose, onSubmit }: ModalProps<number> & { line: StockRequestLine }) {
  const max = Math.min(line.qty_backordered, line.qty_backorder_open, line.warehouse_available ?? 0);
  const [qty, setQty] = useState(String(max));
  return (
    <ConfirmDialog open title={`Reserve backorder · ${line.product_name ?? line.sku}`} busy={busy} error={error} confirmLabel="Reserve stock"
      message={`Reserves available warehouse stock for this line. The reserved quantity moves from backordered to approved. ${line.warehouse_available ?? 0} available now.`}
      onClose={onClose} onConfirm={() => onSubmit(Number(qty))}>
      <Field label={`Quantity (up to ${max})`}>{(fid) => <Input id={fid} type="number" min={1} max={max} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
    </ConfirmDialog>
  );
}

function ReleaseDialog({ line, busy, error, onClose, onSubmit }: ModalProps<{ reason: string; to_backorder: boolean }> & { line: StockRequestLine }) {
  const [toBackorder, setToBackorder] = useState(false);
  return (
    <ConfirmDialog open title={`Release reservation · ${line.product_name ?? line.sku}`} requireReason busy={busy} error={error} confirmLabel="Release stock"
      message={`${line.qty_reserved} reserved unit(s) become available in the warehouse again.`}
      onClose={onClose} onConfirm={(reason) => onSubmit({ reason, to_backorder: toBackorder })}>
      <label className="flex items-center gap-2 text-body">
        <input type="checkbox" className="size-4 accent-ink" checked={toBackorder} onChange={(e) => setToBackorder(e.target.checked)} />
        Keep the quantity on backorder (otherwise it is cancelled)
      </label>
    </ConfirmDialog>
  );
}
