"use client";

import { ArrowLeftRight, CheckCheck, PackageCheck, Printer, Send, Truck, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CheckStockButton } from "@/components/CheckStock";
import { StockAvailability } from "@/components/StockAvailability";
import { ApprovalFields, approvalBody, approvalLabel, approvalReady, blankApproval, type Approval } from "@/components/fulfilment/ApprovalDetails";
import { ConfirmDeliveryModal } from "@/components/fulfilment/ConfirmDeliveryModal";
import { EscalateDialog, escalationText } from "@/components/fulfilment/EscalateDialog";
import { ShipModal } from "@/components/fulfilment/ShipModal";
import { canConfirmCarried, ReceiptView } from "@/components/ReceiptProof";
import { DeliveryNoteActions } from "@/components/Shipping";
import {
  Alert, Badge, Button, ButtonLink, Card, ConfirmDialog, cx, DataTable, DefinitionList, Field, Input, Loading,
  MobileActionBar, Modal, MoreMenu, type MoreMenuItem, PageHeader, Select,
} from "@/components/ui";
import { FlowInline, Timeline, type Step } from "@/components/flow";
import { TyreLabel } from "@/components/pickers";
import { ROLE_LABELS } from "@/config/roles";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Delivery, PurchaseOrder, RequestDetail } from "@/lib/types";

function originLink(r: RequestDetail) {
  if (!r.origin_number) return r.reason === "MANUAL" ? "Manual request" : "—";
  if (r.origin_type === "consignment_sale") return <Link className="link" href={`/sales?sale=${r.origin_id}`}>{r.origin_number}</Link>;
  if (r.origin_type === "transfer") return <Link className="link" href={`/transfers/${r.origin_id}`}>{r.origin_number}</Link>;
  return r.origin_number;
}

/** Raised → Approved → Ready for shipment → Shipped → Delivered, the same steps as a stock request (finding 22). */
function steps(r: RequestDetail): Step[] {
  const ev = (...types: string[]) => [...r.events].reverse().find((e) => types.includes(e.event_type));
  const raised: Step = { label: "Raised", state: "done", at: r.created_at, by: r.raised_by ?? "System" };
  const rejected = ev("REJECTED");
  if (r.status === "CANCELLED") {
    const c = rejected ?? ev("CANCELLED");
    return [raised, { label: rejected ? "Not supplied" : "Cancelled", state: "failed", at: c?.occurred_at, by: c?.actor_name, note: c?.reason }];
  }
  const allocated = ev("APPROVED", "ALLOCATED");
  const approved = !!r.approved_at || r.auto_approved || r.qty_allocated + r.qty_in_transit + r.qty_delivered > 0;
  const shipped = ev("DISPATCHED");
  const delivered = ev("DELIVERED");
  const approvalNote = r.auto_approved ? `Approved automatically${r.origin_number ? ` (replacement for ${r.origin_number})` : ""}` : null;
  return [
    raised,
    { label: "Approved", state: approved ? "done" : "current",
      at: r.approved_at ?? allocated?.occurred_at, by: r.approved_by ?? (r.auto_approved ? null : allocated?.actor_name), note: approvalNote },
    { label: "Ready for shipment", state: r.ready || shipped ? "done" : approved && r.qty_allocated > 0 ? "current" : "pending",
      at: r.ready_at ?? ev("READY_FOR_SHIPMENT")?.occurred_at, by: r.ready_by },
    { label: "Shipped", state: r.qty_in_transit > 0 ? "current" : shipped ? "done" : "pending", at: shipped?.occurred_at, by: shipped?.actor_name },
    { label: "Delivered", state: r.status === "FULFILLED" ? "done" : delivered ? "current" : "pending", at: delivered?.occurred_at, by: delivered?.actor_name },
  ];
}

const SEGMENTS: { label: string; cls: string; value: (r: RequestDetail) => number }[] = [
  { label: "Delivered", cls: "bg-success", value: (r) => r.qty_delivered },
  { label: "In transit", cls: "bg-info", value: (r) => r.qty_in_transit },
  { label: "Allocated", cls: "bg-info/40", value: (r) => r.qty_allocated + r.qty_transfer_covered },
  { label: "Awaiting supply", cls: "bg-warning/60", value: (r) => r.qty_awaiting_supply },
  { label: "Cancelled", cls: "bg-line-strong", value: (r) => r.qty_cancelled },
];

export default function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can, user } = useAuth();
  const { data: r, error, reload } = useApi<RequestDetail>(`/replenishment/requests/${id}`);
  const [dialog, setDialog] = useState<null | "allocate" | "cancel" | "plan" | "approve" | "escalate" | "handback" | "reject" | "ship"
    | { release: number } | { confirm: Delivery }>(null);
  const [qty, setQty] = useState("");
  const [priority, setPriority] = useState("");
  const [expected, setExpected] = useState("");
  const [poLine, setPoLine] = useState("");
  const { data: pos } = useApi<PurchaseOrder[]>(can("replenishment.manage") ? "/purchasing/purchase-orders" : null, { open_only: true });
  const action = useAction();

  if (error) return <Alert>{error}</Alert>;
  if (!r || !user) return <Loading />;
  const open = !["FULFILLED", "CANCELLED"].includes(r.status);
  const staff = !user.reseller_id;
  // Lines of a stock request are approved, shipped and delivered on that stock request.
  const managedOnSrq = r.reason === "STOCK_REQUEST";
  const flow = open && !managedOnSrq;
  const approver = can("replenishment.approve");
  const dispatcher = can("replenishment.dispatch");
  const escalated = !!r.escalated_to_user_id;
  const mayDecide = approver && (!escalated || user.id === r.escalated_to_user_id || user.role === "ADMINISTRATOR");
  const awaiting = r.qty_awaiting_supply > 0;
  const rejectedNote = r.events.find((e) => e.event_type === "REJECTED")?.reason;
  const closeDialog = () => { setDialog(null); action.setError(null); };
  const post = async (path: string, body: unknown = {}) => {
    if (await action.run(() => api.post(path, body))) done();
  };
  const poOptions = (pos ?? []).flatMap((po) => po.lines.filter((l) => l.product_id === r.product_id)
    .map((l) => ({ value: l.id, label: `${po.number} · ${po.supplier_name} · ${l.qty_outstanding} due ${fmtDate(po.expected_date)}` })));
  const done = () => { setDialog(null); reload(); };
  // Cover this backorder with a transfer from another dealer: the transfer form opens already linked to it.
  const coverHref = open && flow && staff && can("transfer.request") && r.qty_awaiting_supply > 0
    ? `/transfers/new?${new URLSearchParams({ destination: String(r.location_id), product: String(r.product_id), qty: String(r.qty_awaiting_supply),
      request: String(r.id), reason: `Covers backorder ${r.number}` })}` : null;
  const chain = staff && ((r.covered_by_transfers ?? []).length > 0 || !!r.fills_request);

  // Phones and tablets in portrait: the first next action sits in the bottom bar, everything else in "More" (desktop
  // order, destructive ones last).
  const approveNow = () => { setQty(String(r.qty_awaiting_supply)); setDialog("approve"); };
  const allocateNow = () => { setQty(String(r.qty_awaiting_supply)); setDialog("allocate"); };
  const confirmable = (r.deliveries ?? []).filter((d) => d.status === "IN_TRANSIT" && can("delivery.confirm")
    && canConfirmCarried(user, d.shipping_method === "SALES_REP" ? d.carried_by_user_id : null));
  const primaries = open ? [
    flow && mayDecide && awaiting && { label: "Approve…", icon: CheckCheck, onSelect: approveNow },
    flow && dispatcher && r.qty_allocated > 0 && { label: "Ship", icon: Truck, onSelect: () => setDialog("ship") },
    can("replenishment.manage") && !approver && !r.awaiting_approval && r.qty_awaiting_supply > 0 && { label: "Allocate from warehouse", onSelect: allocateNow },
  ].filter((x) => !!x) : [];
  const confirmInBar = primaries.length === 0 && confirmable.length === 1;
  const [first, ...otherPrimaries] = primaries;
  const NextIcon = first?.icon;
  const next = first
    ? <Button variant="primary" onClick={first.onSelect}>{NextIcon && <NextIcon aria-hidden />}{first.label}</Button>
    : confirmInBar ? <Button variant="primary" onClick={() => setDialog({ confirm: confirmable[0] })}>Confirm delivery</Button> : null;
  const more: MoreMenuItem[] = open ? [
    ...otherPrimaries,
    ...(staff && flow ? [{ label: "Print pick sheet", href: `/replenishment/${r.id}/print`, icon: Printer }] : []),
    ...(coverHref ? [{ label: "Cover with a transfer", href: coverHref, icon: ArrowLeftRight }] : []),
    ...(flow && approver && awaiting && !escalated && user.role === "WAREHOUSE_MANAGER" ? [{ label: "Send to Relationship Manager", icon: Send, onSelect: () => setDialog("escalate") }] : []),
    ...(flow && escalated && mayDecide ? [{ label: "Hand back to warehouse", onSelect: () => setDialog("handback") }] : []),
    ...(flow && dispatcher && r.qty_allocated > 0 && !r.ready ? [{ label: "Mark ready for shipment", icon: PackageCheck, disabled: action.busy, onSelect: () => post(`/replenishment/requests/${r.id}/ready`) }] : []),
    ...(can("replenishment.manage") ? [{ label: "Priority / supply", onSelect: () => { setPriority(r.priority); setExpected(r.expected_date ?? ""); setPoLine(""); setDialog("plan"); } }] : []),
    ...(flow && mayDecide && awaiting ? [{ label: "Reject request", icon: X, danger: true, onSelect: () => setDialog("reject") }] : []),
    ...(can("replenishment.cancel") && r.qty_awaiting_supply > 0 ? [{ label: "Cancel quantity", danger: true, onSelect: () => { setQty(String(r.qty_awaiting_supply)); setDialog("cancel"); } }] : []),
  ] : [];

  return (
    <>
      <PageHeader mobileActions={open ? <>{can("transfer.request") && <CheckStockButton />}<MoreMenu items={more} /></> : undefined} title={<span className="flex flex-wrap items-center gap-2">{r.number} <Badge value={r.status} /> <Badge value={r.reason} /></span>}
        eyebrow="Replenishment request"
        subtitle={<>{r.qty_required} × {r.product_name} <span className="sku text-label text-ink-secondary">{r.sku}</span> for <Link className="link" href={`/resellers/${r.reseller_id}`}>{r.reseller_name}</Link> ({r.location_code})</>}
        actions={open && <>
          {can("transfer.request") && <CheckStockButton />}
          {staff && flow && <ButtonLink href={`/replenishment/${r.id}/print`}><Printer aria-hidden />Print pick sheet</ButtonLink>}
          {coverHref && <ButtonLink href={coverHref}><ArrowLeftRight aria-hidden />Cover with a transfer</ButtonLink>}
          {flow && approver && awaiting && !escalated && user.role === "WAREHOUSE_MANAGER" &&
            <Button onClick={() => setDialog("escalate")}><Send aria-hidden />Send to Relationship Manager</Button>}
          {flow && escalated && mayDecide && <Button onClick={() => setDialog("handback")}>Hand back to warehouse</Button>}
          {flow && mayDecide && awaiting && <>
            <Button variant="danger" onClick={() => setDialog("reject")}><X aria-hidden />Reject</Button>
            <Button variant="primary" onClick={() => { setQty(String(r.qty_awaiting_supply)); setDialog("approve"); }}><CheckCheck aria-hidden />Approve…</Button>
          </>}
          {flow && dispatcher && r.qty_allocated > 0 && <>
            {!r.ready && <Button onClick={() => post(`/replenishment/requests/${r.id}/ready`)} disabled={action.busy}><PackageCheck aria-hidden />Mark ready for shipment</Button>}
            <Button variant="primary" onClick={() => setDialog("ship")}><Truck aria-hidden />Ship</Button>
          </>}
          {can("replenishment.manage") && !approver && !r.awaiting_approval && r.qty_awaiting_supply > 0 && <Button variant="primary" onClick={() => { setQty(String(r.qty_awaiting_supply)); setDialog("allocate"); }}>Allocate from warehouse</Button>}
          {can("replenishment.manage") && <Button onClick={() => { setPriority(r.priority); setExpected(r.expected_date ?? ""); setPoLine(""); setDialog("plan"); }}>Priority / supply</Button>}
          {can("replenishment.cancel") && r.qty_awaiting_supply > 0 && <Button variant="danger" onClick={() => { setQty(String(r.qty_awaiting_supply)); setDialog("cancel"); }}>Cancel quantity</Button>}
        </>} />
      <Alert>{dialog === null ? action.error : null}</Alert>
      {managedOnSrq && r.origin_id && (
        <Alert tone="info">Approved, shipped and delivered on its stock request: <Link className="link font-medium" href={`/stock-requests/${r.origin_id}`}>{r.origin_number}</Link></Alert>
      )}
      {staff && flow && escalated && <Alert tone="warn">{escalationText(r)}</Alert>}
      {staff && flow && r.awaiting_approval && !escalated && <Alert tone="info">Raised by {r.raised_by ?? "the dealer"}: waiting for approval.</Alert>}
      {!staff && rejectedNote && <Alert tone="info">{rejectedNote}</Alert>}
      {!managedOnSrq && <Card className="mb-4"><Timeline steps={steps(r)} /></Card>}
      {staff && (r.approved_by || r.auto_approved) && (
        <Card title="Approval" className="mb-4">
          {r.auto_approved
            ? <p className="text-label text-ink-secondary">Approved automatically{r.origin_number ? ` (replacement for ${r.origin_number})` : ""}.</p>
            : <DefinitionList columns={2} items={[
                ["Approved by", `${r.approved_by ?? "—"} · ${fmtDateTime(r.approved_at)}`],
                ["How", approvalLabel(r.approval_method)], ["Spoke to", r.approval_contact ?? "—"], ["Comments", r.approval_comments],
              ]} />}
        </Card>
      )}
      {chain && (
        <Card title="Transfer link" icon={ArrowLeftRight} className="mb-4"
          subtitle="Who supplied this dealer, and the replacement owed to the dealer who gave the tyres">
          <ul className="divide-y divide-line text-body">
            {(r.covered_by_transfers ?? []).map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 first:pt-0 last:pb-0">
                <span>Covered by <Link className="link font-medium" href={`/transfers/${t.id}`}>{t.number}</Link>
                  {" "}({t.quantity} from {t.source_reseller_name ?? "a dealer not chosen yet"})</span>
                <Badge value={t.status} />
                <span className="text-ink-secondary">
                  {t.replacement
                    ? <>{t.source_reseller_name}&rsquo;s replacement <Link className="link" href={`/replenishment/${t.replacement.id}`}>{t.replacement.number}</Link>
                      {" "}<Badge value={t.replacement.status} />{t.replacement.qty_awaiting_supply > 0 && <> · {t.replacement.qty_awaiting_supply} on backorder</>}</>
                    : "Their replacement is raised when the tyres are collected"}
                </span>
              </li>
            ))}
            {r.fills_request && (
              <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 first:pt-0 last:pb-0">
                <span>Replacement for {originLink(r)}, which filled <Link className="link font-medium" href={`/replenishment/${r.fills_request.id}`}>{r.fills_request.number}</Link>
                  {" "}for {r.fills_request.reseller_name}</span>
                <Badge value={r.fills_request.status} />
              </li>
            )}
          </ul>
        </Card>
      )}
      <Card className="mb-4">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center">
          <div className="lg:w-96"><FlowInline from="Warehouse" to={<>{r.reseller_name} · {r.location_code}</>} />
            <div className="mt-1 text-caption text-ink-muted">{r.product_name}</div></div>
          <div className="min-w-0 flex-1">
            <div className="flex h-3 overflow-hidden rounded-full bg-neutral-soft" role="img"
              aria-label={`${r.qty_delivered} delivered, ${r.qty_in_transit} in transit, ${r.qty_allocated + r.qty_transfer_covered} allocated, ${r.qty_awaiting_supply} awaiting supply of ${r.qty_required}`}>
              {SEGMENTS.map((seg) => { const v = seg.value(r); return v > 0 ? <span key={seg.label} className={seg.cls} style={{ width: `${(v / Math.max(r.qty_required, 1)) * 100}%` }} /> : null; })}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-label">
              {SEGMENTS.map((seg) => (
                <span key={seg.label} className="inline-flex items-center gap-1.5 text-ink-secondary">
                  <span className={cx("size-2.5 rounded-sm", seg.cls)} aria-hidden />{seg.label} <span className="num font-semibold text-ink">{seg.value(r)}</span>
                </span>
              ))}
              <span className="ml-auto text-ink-muted">of <span className="num font-semibold text-ink">{r.qty_required}</span> required</span>
            </div>
          </div>
        </div>
      </Card>
      {open && <div className="mb-4"><StockAvailability productIds={[r.product_id]} dealerLocationId={r.location_id}
        requested={{ [r.product_id]: r.qty_awaiting_supply || r.qty_required - r.qty_delivered - r.qty_cancelled }} /></div>}
      {(r.deliveries ?? []).length > 0 && (
        <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
          {(r.deliveries ?? []).map((d) => (
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
              <div className="mt-3"><DeliveryNoteActions delivery={d} onChanged={reload} /></div>
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
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Details">
          <DefinitionList columns={1} items={[
            ["Reason", <span key="r">{humanize(r.reason)}{r.first_supply && <> <Badge value="LATEST_STOCK" label="Latest stock" /></>}</span>], ["Originating record", originLink(r)],
            ["Raised by", r.raised_by ? `${r.raised_by}${r.raised_by_role ? ` · ${ROLE_LABELS[r.raised_by_role]}` : ""}` : "System"], ["Priority", <Badge key="p" value={r.priority} />],
            ["Expected supply", fmtDate(r.expected_date)], ["Supply reference", r.purchase_order_line_id ? `PO line #${r.purchase_order_line_id}` : "—"],
            ["Created", fmtDateTime(r.created_at)], ["Age", `${r.age_days} day(s)`], ["Closed", fmtDateTime(r.closed_at)], ["Notes", r.notes],
          ]} />
        </Card>
        <Card title="History" padded={false}>
          <DataTable label="Request history" search={false} rows={r.events} rowKey={(e) => e.id} columns={[
            { key: "t", header: "When", cell: (e) => <span className="whitespace-nowrap text-caption">{fmtDateTime(e.occurred_at)}</span> },
            { key: "e", header: "Event", cell: (e) => humanize(e.event_type) },
            { key: "q", header: "Qty", align: "right", cell: (e) => e.quantity ?? "" },
            { key: "r", header: "Reference / reason", className: "min-w-48 whitespace-normal", cell: (e) => <span className="text-caption">{e.reference_number}{e.reason && <span className="text-ink-muted"> {e.reason}</span>}</span> },
            { key: "a", header: "By", cell: (e) => <span className="text-caption">{e.actor_name}</span> },
          ]} />
        </Card>
        <Card title="Warehouse allocations" padded={false}>
          <DataTable mobile="cards" label="Allocations" search={false} rows={r.allocations} rowKey={(a) => a.id} empty="No allocations yet" columns={[
            { key: "d", mobile: "primary", header: "Allocated", cell: (a) => fmtDateTime(a.created_at) },
            { key: "q", mobile: "field", mobileOrder: 1, header: "Qty", align: "right", cell: (a) => a.quantity },
            { key: "dp", mobile: "field", mobileOrder: 2, header: "Dispatched", align: "right", cell: (a) => a.dispatched_qty },
            { key: "rl", header: "Released", align: "right", cell: (a) => a.released_qty },
            { key: "s", mobile: "status", header: "Status", cell: (a) => <Badge value={a.status} /> },
            { key: "x", mobile: "action", header: "", cell: (a) => a.open_qty > 0 && can("replenishment.manage") && <Button size="sm" variant="ghost" onClick={() => setDialog({ release: a.id })}>Release</Button> },
          ]} />
        </Card>
        <Card title="Deliveries (partial fulfilments)" padded={false}>
          <DataTable mobile="cards" label="Deliveries" search={false} rows={r.delivery_lines} rowKey={(d) => `${d.delivery_id}-${d.qty_dispatched}`} empty="Nothing dispatched yet" columns={[
            { key: "n", mobile: "primary", header: "Delivery", cell: (d) => d.delivery_number },
            { key: "dp", mobile: "field", mobileOrder: 1, header: "Dispatched", align: "right", cell: (d) => d.qty_dispatched },
            { key: "rc", mobile: "field", mobileOrder: 2, header: "Received", align: "right", cell: (d) => d.qty_received },
            { key: "o", mobile: "field", mobileOrder: 3, header: "Unresolved", align: "right", cell: (d) => d.qty_open },
            { key: "s", mobile: "status", header: "Status", cell: (d) => <Badge value={d.delivery_status} /> },
          ]} />
        </Card>
      </div>

      {next && <MobileActionBar desktop="hidden">{next}</MobileActionBar>}

      {dialog === "approve" && <ApproveModal r={r} busy={action.busy} error={action.error} onClose={closeDialog}
        onSubmit={(body) => post(`/replenishment/requests/${r.id}/approve`, body)} />}
      {dialog === "escalate" && <EscalateDialog number={r.number} busy={action.busy} error={action.error} onClose={closeDialog}
        onSubmit={(body) => post(`/replenishment/requests/${r.id}/escalate`, body)} />}
      <ConfirmDialog open={dialog === "handback"} title="Hand back to the warehouse" busy={action.busy} error={action.error} confirmLabel="Hand back"
        message="The warehouse can decide this request again." onClose={closeDialog}
        onConfirm={() => post(`/replenishment/requests/${r.id}/hand-back`, { note: null })} />
      <ConfirmDialog open={dialog === "reject"} title={`Reject ${r.number}`} danger requireReason busy={action.busy} error={action.error}
        confirmLabel="Reject request" onClose={closeDialog} onConfirm={(reason) => post(`/replenishment/requests/${r.id}/reject`, { reason })}
        message={`The ${r.qty_awaiting_supply} unit(s) still awaiting supply are not supplied. The dealer gets a kind standard message; your reason stays with the staff.`} />
      {dialog === "ship" && <ShipModal number={r.number} resellerId={r.reseller_id}
        lines={[{ key: r.id, sku: r.sku, productName: r.product_name, reserved: r.qty_allocated }]}
        busy={action.busy} error={action.error} onClose={closeDialog}
        onSubmit={(x) => post(`/replenishment/requests/${r.id}/ship`, {
          ...x.shipping, carrier: x.carrier, tracking_number: x.tracking_number, notes: x.notes, quantity: x.quantities[0]?.quantity || null,
        })} />}
      {typeof dialog === "object" && dialog && "confirm" in dialog && <ConfirmDeliveryModal d={dialog.confirm} busy={action.busy} error={action.error}
        onClose={closeDialog} onSubmit={({ reference, ...body }) => post(`/replenishment/deliveries/${dialog.confirm.id}/receive`, { ...body, delivery_reference: reference })} />}
      <ConfirmDialog open={dialog === "allocate"} title="Allocate warehouse stock" busy={action.busy} error={action.error} confirmLabel="Reserve stock"
        message="Reserves available warehouse stock for this request. Only available (unreserved, unblocked) stock can be allocated."
        onClose={() => setDialog(null)}
        onConfirm={async () => { if (await action.run(() => api.post(`/replenishment/requests/${r.id}/allocate`, { quantity: Number(qty) }))) done(); }}>
        <Field label={`Quantity (awaiting ${r.qty_awaiting_supply})`}>{(fid) => <Input id={fid} type="number" min={1} max={r.qty_awaiting_supply} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
      </ConfirmDialog>
      <ConfirmDialog open={dialog === "cancel"} title="Cancel outstanding quantity" danger requireReason busy={action.busy} error={action.error} confirmLabel="Cancel quantity"
        message="Only quantity still awaiting supply can be cancelled. Release allocations or resolve deliveries first for the rest."
        onClose={() => setDialog(null)}
        onConfirm={async (reason) => { if (await action.run(() => api.post(`/replenishment/requests/${r.id}/cancel`, { quantity: Number(qty), reason }))) done(); }}>
        <Field label="Quantity">{(fid) => <Input id={fid} type="number" min={1} max={r.qty_awaiting_supply} value={qty} onChange={(e) => setQty(e.target.value)} />}</Field>
      </ConfirmDialog>
      <ConfirmDialog open={dialog === "plan"} title="Priority and expected supply" requireReason busy={action.busy} error={action.error} confirmLabel="Save"
        onClose={() => setDialog(null)}
        onConfirm={async (reason) => {
          const body: Record<string, unknown> = { reason };
          if (priority !== r.priority) body.priority = priority;
          if (expected && expected !== r.expected_date) body.expected_date = expected;
          if (!expected && r.expected_date) body.clear_expected_date = true;
          if (poLine) body.purchase_order_line_id = Number(poLine);
          if (await action.run(() => api.post(`/replenishment/requests/${r.id}/planning`, body))) done();
        }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Priority">{(fid) => <Select id={fid} value={priority} onChange={(e) => setPriority(e.target.value)} options={["URGENT", "HIGH", "NORMAL", "LOW"].map((p) => ({ value: p, label: humanize(p) }))} />}</Field>
          <Field label="Expected supply date">{(fid) => <Input id={fid} type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />}</Field>
        </div>
        <Field label="Link to incoming purchase order" hint="Incoming stock is not on hand; linking only records the expected supply.">{(fid) => <Select id={fid} value={poLine} onChange={(e) => setPoLine(e.target.value)} placeholder="— none —" options={poOptions} />}</Field>
      </ConfirmDialog>
      <ConfirmDialog open={typeof dialog === "object" && dialog !== null && "release" in dialog} title="Release allocation" requireReason busy={action.busy} error={action.error} confirmLabel="Release"
        message="The reserved warehouse stock becomes available again and the quantity returns to awaiting supply."
        onClose={() => setDialog(null)}
        onConfirm={async (reason) => { if (typeof dialog === "object" && dialog && "release" in dialog && await action.run(() => api.post(`/replenishment/allocations/${dialog.release}/release`, { reason }))) done(); }} />
    </>
  );
}

/** Allocate warehouse stock and record how it was approved (findings 17 and 22). */
function ApproveModal({ r, busy, error, onClose, onSubmit }: {
  r: RequestDetail; busy: boolean; error: string | null; onClose: () => void; onSubmit: (body: unknown) => void;
}) {
  const [qty, setQty] = useState(String(r.qty_awaiting_supply));
  const [approval, setApproval] = useState<Approval>(blankApproval);
  const q = Number(qty);
  const invalid = !Number.isInteger(q) || q < 1 || q > r.qty_awaiting_supply || !approvalReady(approval);
  return (
    <Modal open title={`Approve ${r.number}`} description="Reserves warehouse stock for this request now. The rest stays awaiting supply." onClose={onClose}
      footer={<><Button onClick={onClose}>Back</Button>
        <Button variant="primary" disabled={busy || invalid} onClick={() => onSubmit({ quantity: q, approval: approvalBody(approval) })}>
          {busy ? "Saving…" : "Approve and reserve"}</Button></>}>
      <Alert>{error}</Alert>
      <StockAvailability productIds={[r.product_id]} dealerLocationId={r.location_id} requested={{ [r.product_id]: r.qty_awaiting_supply }} />
      <Field label={`Quantity to approve (awaiting ${r.qty_awaiting_supply})`} required>
        {(fid) => <Input id={fid} type="number" min={1} max={r.qty_awaiting_supply} value={qty} onChange={(e) => setQty(e.target.value)} />}
      </Field>
      <ApprovalFields value={approval} onChange={setApproval} />
    </Modal>
  );
}
