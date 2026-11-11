"use client";

import { ArrowLeft, Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Alert, Button, Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Reseller, StockRequestDetail } from "@/lib/types";

/** Printable pick sheet for the warehouse (finding 16). Staff only; no prices. */
export default function PickSheetPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const staff = !!user && !user.reseller_id;
  const { data: r, error } = useApi<StockRequestDetail>(staff ? `/stock-requests/${id}` : null);
  const { data: dealer } = useApi<Reseller>(r ? `/resellers/${r.reseller_id}` : null);
  if (!staff) return <Alert>The pick sheet is for dealership staff.</Alert>;
  if (error) return <Alert>{error}</Alert>;
  if (!r) return <Loading />;
  const shop = dealer?.locations.find((l) => l.id === r.location_id);
  const decided = !!r.decision;
  return (
    <>
      <div className="no-print mb-4 flex items-center justify-between">
        <Link href={`/stock-requests/${r.id}`} className="inline-flex items-center gap-1.5 text-label text-ink-secondary hover:text-ink"><ArrowLeft className="size-3.5" aria-hidden />{r.number}</Link>
        <Button variant="primary" onClick={() => window.print()}><Printer aria-hidden />Print</Button>
      </div>
      <article className="mx-auto max-w-4xl rounded-card border border-line bg-surface p-6 text-label print:border-0 print:p-0 sm:p-10">
        <header className="flex items-start justify-between gap-6 border-b border-line-strong pb-4">
          <div>
            <Logo className="mb-2 h-7" />
            <h1 className="text-display-compact font-bold">Pick sheet</h1>
            <div>Request <b>{r.number}</b> · {humanize(r.status)}</div>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-right">
            <dt className="text-ink-muted">Priority</dt><dd className="font-medium">{humanize(r.priority)}</dd>
            <dt className="text-ink-muted">Required by</dt><dd>{fmtDate(r.required_date)}</dd>
            <dt className="text-ink-muted">Requested by</dt><dd>{r.created_by ?? "—"}</dd>
            <dt className="text-ink-muted">Printed</dt><dd>{fmtDateTime(new Date().toISOString())}</dd>
          </dl>
        </header>
        <section className="grid grid-cols-2 gap-6 border-b border-line py-4">
          <div>
            <div className="text-caption tracking-wide text-ink-muted uppercase">Dealer</div>
            <div className="font-semibold">{r.reseller_name}</div>
            <div>Account {dealer?.account_ref ?? "…"}</div>
          </div>
          <div>
            <div className="text-caption tracking-wide text-ink-muted uppercase">Shop and delivery address</div>
            <div className="font-semibold">{shop?.name ?? r.location_code} <span className="sku text-label">{r.location_code}</span></div>
            <div className="whitespace-pre-line">{r.shipping_address ?? [shop?.address_line1, shop?.address_line2, shop?.city, shop?.postcode].filter(Boolean).join(", ")}</div>
          </div>
        </section>
        <table className="mt-4 w-full">
          <thead className="border-y border-line-strong text-left text-caption text-ink-secondary uppercase">
            <tr><th className="py-2 pr-2">#</th><th className="pr-2">SKU</th><th className="pr-2">Tyre</th><th className="pr-2 text-right">Requested</th>
              <th className="pr-2 text-right">Approved</th><th className="pr-2 text-center">Picked</th><th>Notes</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {r.lines.map((l) => (
              <tr key={l.id}>
                <td className="py-2.5 pr-2 align-top">{l.line_no}</td>
                <td className="pr-2 align-top sku text-label">{l.sku}</td>
                <td className="pr-2 align-top">{l.product_name}</td>
                <td className="num pr-2 text-right align-top">{l.qty_requested}</td>
                <td className="num pr-2 text-right align-top">{decided ? l.qty_approved : ""}</td>
                <td className="pr-2 text-center align-top text-heading leading-none">☐</td>
                <td className="w-40 align-top text-caption">{l.notes ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {r.notes && <p className="mt-3 text-ink-secondary">Request notes: {r.notes}</p>}
        <footer className="mt-10 grid grid-cols-3 gap-6 text-label">
          {["Picked by", "Checked by", "Date"].map((label) => (
            <div key={label}><div className="h-8 border-b border-ink" /><div className="mt-1 text-ink-muted">{label}</div></div>
          ))}
        </footer>
      </article>
    </>
  );
}
