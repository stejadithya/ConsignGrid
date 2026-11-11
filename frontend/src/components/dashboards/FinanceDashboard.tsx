"use client";

import { FileCheck2, ReceiptText } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Invoice, UninvoicedLine } from "@/lib/types";
import { Alert, Badge, Card, DataTable, Loading } from "../ui";
import { DashboardHeader, JobList, plural, RoleBanner, Section } from "./shared";

/** The Finance Manager's view: what to bill in Xero, invoice records waiting for a Xero number, and what was invoiced. */
export function FinanceDashboard() {
  const { user } = useAuth();
  const { data: lines, error } = useApi<UninvoicedLine[]>("/invoices/uninvoiced");
  const { data: invoices } = useApi<Invoice[]>("/invoices");

  const byDealer = useMemo(() => {
    const by = new Map<number, { id: number; name: string; tyres: number; sales: Set<number>; oldest: number }>();
    for (const l of lines ?? []) {
      const x = by.get(l.reseller_id) ?? { id: l.reseller_id, name: l.reseller_name ?? "—", tyres: 0, sales: new Set(), oldest: 0 };
      x.tyres += l.quantity; x.sales.add(l.sale_id); x.oldest = Math.max(x.oldest, l.age_days);
      by.set(l.reseller_id, x);
    }
    return [...by.values()].sort((a, b) => b.oldest - a.oldest || b.tyres - a.tyres);
  }, [lines]);
  const awaitingXero = useMemo(() => (invoices ?? []).filter((i) => i.status !== "VOID" && !i.external_reference), [invoices]);
  const recent = useMemo(() => (invoices ?? []).filter((i) => i.status === "ISSUED")
    .sort((a, b) => (b.issued_at ?? "").localeCompare(a.issued_at ?? "")).slice(0, 8), [invoices]);

  if (!user) return null;
  const tyres = (lines ?? []).reduce((a, l) => a + l.quantity, 0);
  const ym = new Date().toISOString().slice(0, 7);
  const invoicedThisMonth = (invoices ?? []).filter((i) => i.status === "ISSUED" && (i.issued_at ?? "").startsWith(ym)).length;
  const tyresOf = (i: Invoice) => i.lines.reduce((a, l) => a + l.quantity, 0);

  return (
    <>
      <DashboardHeader name={user.full_name} subtitle="What to bill in Xero, and invoice records still waiting for their Xero number." />
      <Alert>{error}</Alert>
      {!lines && !error && <Loading label="Loading dashboard…" />}
      {lines && (
        <>
          <RoleBanner theme="finance" figures={[
            { label: "Tyres sold, not invoiced", value: tyres.toLocaleString(), href: "/invoices", hint: plural(byDealer.length, "dealer"), tone: tyres ? "warn" : undefined },
            { label: "Dealers to invoice", value: byDealer.length, href: "/invoices" },
            { label: "Waiting for a Xero number", value: awaitingXero.length, href: "/invoices", tone: awaitingXero.length ? "warn" : undefined },
            { label: "Invoiced this month", value: invoicedThisMonth, href: "/invoices" },
          ]} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
            <Section title="To do" className="xl:col-span-2" description="Each line opens the screen to do it">
              <JobList jobs={[
                { label: "Create invoice records", value: byDealer.length, hint: `${plural(tyres, "tyre")} sold and not yet invoiced`, href: "/invoices", icon: ReceiptText },
                { label: "Add Xero numbers", value: awaitingXero.length, hint: "Invoice records not yet matched to Xero", href: "/invoices", icon: FileCheck2, urgent: awaitingXero.length > 0 },
              ]} />
            </Section>
            <Section title="Sold, not invoiced, by dealer" className="xl:col-span-3">
              <Card padded={false}>
                <DataTable mobile="cards" label="Dealers to invoice" search={false} rows={byDealer} rowKey={(x) => x.id} pageSize={8}
                  empty="Nothing waiting to be invoiced" emptyHint="Tyres dealers sell appear here until they are invoiced."
                  columns={[
                    { key: "n", mobile: "primary", header: "Dealer", cell: (x) => <Link className="link font-medium" href={`/resellers/${x.id}`}>{x.name}</Link> },
                    { key: "t", mobile: "field", mobileOrder: 1, header: "Tyres", align: "right", cell: (x) => <Link className="link num" href="/invoices">{x.tyres}</Link> },
                    { key: "s", mobile: "field", mobileOrder: 2, header: "Sales", align: "right", cell: (x) => <Link className="link num" href={`/sales?reseller=${x.id}`}>{x.sales.size}</Link> },
                    { key: "o", mobile: "field", mobileOrder: 3, header: "Oldest", align: "right", cell: (x) => <span className={x.oldest > 30 ? "num font-semibold text-warning" : "num"}>{plural(x.oldest, "day")}</span> },
                  ]} />
              </Card>
            </Section>
          </div>

          <Section title="Invoice records">
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Card title="Waiting for a Xero number" padded={false}>
                <DataTable mobile="cards" label="Invoice records to complete" search={false} rows={invoices ? awaitingXero : null} rowKey={(i) => i.id} pageSize={6}
                  empty="All matched to Xero" emptyHint="Invoice records without a Xero number appear here."
                  columns={[
                    { key: "n", mobile: "primary", header: "Record", cell: (i) => <Link className="link font-medium" href={`/invoices/${i.id}`}>{i.number}</Link> },
                    { key: "d", mobile: "secondary", header: "Dealer", cell: (i) => i.bill_to_name },
                    { key: "c", mobile: "field", mobileOrder: 1, header: "Created", cell: (i) => <span className="text-ink-secondary">{fmtDate(i.invoice_date)}</span> },
                    { key: "q", mobile: "field", mobileOrder: 2, header: "Tyres", align: "right", cell: (i) => <Link className="link num" href={`/invoices/${i.id}`}>{tyresOf(i)}</Link> },
                    { key: "s", mobile: "status", header: "Status", cell: (i) => <Badge value={i.status} /> },
                  ]} />
              </Card>
              <Card title="Recently invoiced" padded={false}>
                <DataTable mobile="cards" label="Recently invoiced" search={false} rows={invoices ? recent : null} rowKey={(i) => i.id} pageSize={8}
                  empty="Nothing invoiced yet" emptyHint="Invoice records appear here once they are invoiced."
                  columns={[
                    { key: "n", mobile: "primary", header: "Record", cell: (i) => <Link className="link font-medium" href={`/invoices/${i.id}`}>{i.number}</Link> },
                    { key: "d", mobile: "secondary", header: "Dealer", cell: (i) => i.bill_to_name },
                    { key: "x", mobile: "field", mobileOrder: 1, header: "Xero no.", cell: (i) => <span className="sku text-label">{i.external_reference ?? "—"}</span> },
                    { key: "w", mobile: "field", mobileOrder: 2, header: "Invoiced", cell: (i) => <span className="text-ink-secondary">{i.issued_at ? fmtDateTime(i.issued_at) : "—"}</span> },
                  ]} />
              </Card>
            </div>
          </Section>
        </>
      )}
    </>
  );
}
