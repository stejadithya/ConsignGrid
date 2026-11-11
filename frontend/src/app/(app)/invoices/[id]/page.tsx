"use client";

import { Printer } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Alert, Badge, Button, ConfirmDialog, Field, Input, Loading, MobileActionBar, Modal, MoreMenu, type MoreMenuItem,
  PageHeader,
} from "@/components/ui";
import { Logo } from "@/components/Logo";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Invoice } from "@/lib/types";
import { ShopLabel } from "@/components/pickers";

const STATUS: Record<string, string> = { DRAFT: "Draft", ISSUED: "Invoiced in Xero", VOID: "Void" };

/** Printable invoice summary for Xero: the sold tyres (quantities) to bill. Prices live in Xero (D2). */
export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { data: inv, error, setData } = useApi<Invoice>(`/invoices/${id}`);
  const [dialog, setDialog] = useState<null | "issue" | "void" | "ref">(null);
  const [ref, setRef] = useState("");
  const action = useAction();
  if (error) return <Alert>{error}</Alert>;
  if (!inv) return <Loading />;
  const lines = inv.lines.filter((l) => l.is_active || inv.status === "VOID");

  const issue = () => { setRef(""); action.setError(null); setDialog("issue"); };
  // Phones and tablets in portrait: "Mark as invoiced in Xero" in the bottom bar, the rest in "More".
  const more: MoreMenuItem[] = [
    { label: "Print", icon: Printer, onSelect: () => window.print() },
    ...(inv.status === "ISSUED" && can("invoice.create") ? [{ label: "Correct Xero number", onSelect: () => { setRef(inv.external_reference ?? ""); setDialog("ref"); } }] : []),
    ...(inv.status !== "VOID" && can("invoice.void") ? [{ label: "Void invoice record", danger: true, onSelect: () => setDialog("void") }] : []),
  ];
  const canIssue = inv.status === "DRAFT" && can("invoice.create");

  return (
    <>
      <PageHeader eyebrow="Invoice record" mobileActions={<MoreMenu items={more} />} title={<span className="flex items-center gap-2">{inv.number} <Badge value={inv.status} label={STATUS[inv.status]} /></span>}
        actions={<>
          <Button onClick={() => window.print()}>Print</Button>
          {canIssue && <Button variant="primary" onClick={issue}>Mark as invoiced in Xero</Button>}
          {inv.status === "ISSUED" && can("invoice.create") && <Button onClick={() => { setRef(inv.external_reference ?? ""); setDialog("ref"); }}>Correct Xero number</Button>}
          {inv.status !== "VOID" && can("invoice.void") && <Button variant="danger" onClick={() => setDialog("void")}>Void</Button>}
        </>} />
      <Alert>{action.error}</Alert>
      {inv.status === "VOID" && <Alert tone="warn">Voided {fmtDateTime(inv.voided_at)} by {inv.voided_by}: {inv.void_reason}. The sale lines were released for re-invoicing.</Alert>}
      <article className="mx-auto max-w-4xl rounded-card border border-line bg-surface p-6 shadow-sm print:border-0 print:shadow-none sm:p-10">
        <header className="flex flex-col justify-between gap-6 border-b border-line pb-6 sm:flex-row">
          <div>
            <Logo className="mb-3 h-8" />
            <div className="text-heading font-semibold">{inv.issuer_name}</div>
            <div className="whitespace-pre-line text-body text-ink-secondary">{inv.issuer_details}</div>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-display-compact font-bold">Invoice summary for Xero</div>
            <div className="mt-1 text-body">Record <b>{inv.number}</b> · {STATUS[inv.status]}</div>
            <div className="text-body">Created {fmtDate(inv.invoice_date)}</div>
            {inv.xero_reference && <div className="text-body">Xero no. <b className="sku">{inv.xero_reference}</b>
              {inv.xero_recorded_by && <span className="text-caption text-ink-muted"> · {inv.xero_recorded_by}, {fmtDateTime(inv.xero_recorded_at)}</span>}</div>}
          </div>
        </header>
        <section className="py-4 text-body">
          <div className="text-caption uppercase tracking-wide text-ink-muted">Dealer</div>
          <div className="font-semibold">{inv.bill_to_name}</div>
          <div>Account ref. <b className="sku">{inv.bill_to_account_ref}</b></div>
          {inv.bill_to_address && <div className="whitespace-pre-line text-ink-secondary">{inv.bill_to_address}</div>}
          {inv.bill_to_tax_number && <div>Tax no. {inv.bill_to_tax_number}</div>}
        </section>
        {/* Focusable so keyboard users can scroll the lines sideways on a phone. */}
        <div className="overflow-x-auto focus-visible:focus-ring" tabIndex={0} role="region" aria-label="Invoice lines, scrolls sideways">
          <table className="min-w-full text-body">
            <thead className="border-y border-line-strong text-left text-caption uppercase text-ink-secondary">
              <tr><th className="py-2 pr-2">SKU</th><th className="pr-2">Tyre</th><th className="pr-2 text-right">Qty</th>
                <th className="pr-2">Sale no.</th><th className="pr-2">Sale date</th><th>Shop</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lines.map((l) => (
                <tr key={l.id} className={l.is_active ? "" : "text-ink-muted line-through"}>
                  <td className="py-2 pr-2 align-top sku text-label">{l.sku}</td>
                  <td className="pr-2 align-top">{l.description}</td>
                  <td className="num pr-2 text-right align-top font-medium">{l.quantity}</td>
                  <td className="pr-2 align-top text-caption">{l.sale_number}</td>
                  <td className="pr-2 align-top text-caption">{fmtDate(l.sale_date)}</td>
                  <td className="align-top text-caption"><ShopLabel inline code={l.location_code} withDealer={false} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex justify-end">
          <dl className="w-64 text-body">
            <div className="flex justify-between border-t border-line-strong py-1 font-semibold"><dt>Total tyres</dt><dd className="num">{lines.filter((l) => l.is_active).reduce((a, l) => a + l.quantity, 0)}</dd></div>
          </dl>
        </div>
        {inv.notes && <p className="mt-4 text-body text-ink-secondary">{inv.notes}</p>}
        <p className="mt-6 text-caption text-ink-muted">Consignment stock invoiced on confirmed sale; prices are set in Xero. Created {fmtDateTime(inv.created_at)} by {inv.created_by}{inv.issued_at && `; marked as invoiced in Xero ${fmtDateTime(inv.issued_at)} by ${inv.issued_by}`}.</p>
      </article>
      {canIssue && <MobileActionBar desktop="hidden"><Button variant="primary" onClick={issue}>Mark as invoiced in Xero</Button></MobileActionBar>}
      <Modal open={dialog === "issue"} title="Mark as invoiced in Xero" onClose={() => setDialog(null)}
        description="Create the invoice in Xero first, then enter its Xero number here. The record's lines can then only be released by voiding it."
        footer={<><Button onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="primary" disabled={action.busy || !ref.trim()}
            onClick={async () => { const r = await action.run(() => api.post<Invoice>(`/invoices/${inv.id}/issue`, { xero_reference: ref.trim() })); if (r) { setData(r); setDialog(null); } }}>
            {action.busy ? "Saving…" : "Mark as invoiced"}</Button></>}>
        <Alert>{action.error}</Alert>
        <Field label="Xero invoice number" required>{(fid) => <Input id={fid} value={ref} maxLength={100} placeholder="e.g. INV-0042" onChange={(e) => setRef(e.target.value)} />}</Field>
      </Modal>
      <ConfirmDialog open={dialog === "void"} title="Void invoice" danger requireReason busy={action.busy} error={action.error} confirmLabel="Void invoice"
        message="The invoice is kept for audit and its sale lines return to 'sold, not invoiced'." onClose={() => setDialog(null)}
        onConfirm={async (reason) => { const r = await action.run(() => api.post<Invoice>(`/invoices/${inv.id}/void`, { reason })); if (r) { setData(r); setDialog(null); } }} />
      <ConfirmDialog open={dialog === "ref"} title="Correct the Xero number" busy={action.busy} error={action.error} confirmLabel="Save" onClose={() => setDialog(null)}
        onConfirm={async () => { const r = await action.run(() => api.put<Invoice>(`/invoices/${inv.id}/external-reference`, { external_reference: ref })); if (r) { setData(r); setDialog(null); } }}>
        <Field label="Xero invoice number">{(fid) => <Input id={fid} value={ref} onChange={(e) => setRef(e.target.value)} />}</Field>
      </ConfirmDialog>
    </>
  );
}
