"use client";

import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { TransfersTable } from "@/components/tables";
import { CheckStockButton } from "@/components/CheckStock";
import { Alert, ButtonLink, Card, FilterField, MetricStrip, PageHeader, QuickFilters, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Transfer } from "@/lib/types";

type QF = "all" | "REQUESTED" | "APPROVED" | "IN_TRANSIT" | "RECEIVED_WITH_DISCREPANCY";

export default function TransfersPage() {
  const { can } = useAuth();
  const [status, setStatus] = useState("open");
  const [qf, setQf] = useState<QF>("all");
  const { data, error } = useApi<Transfer[]>("/transfers", status === "open" ? { open_only: true } : { status: status === "all" ? undefined : status });
  const count = (s: QF) => (data ?? []).filter((t) => t.status === s).length;
  const rows = useMemo(() => (qf === "all" ? data : data?.filter((t) => t.status === qf)) ?? null, [data, qf]);
  const owed = (data ?? []).filter((t) => t.source_request && t.source_request.qty_outstanding > 0).length;

  return (
    <>
      <PageHeader title="Stock transfers"
        subtitle="Dealership-controlled movement of unsold consignment stock between dealers. A transfer is not a sale: nobody is invoiced for it, and the supplying dealer is owed replacement stock."
        actions={can("transfer.request") && <><CheckStockButton /><ButtonLink href="/transfers/new" variant="primary"><Plus aria-hidden />New transfer</ButtonLink></>} />
      <Alert>{error}</Alert>
      {data && status === "open" && (
        <MetricStrip items={[
          { label: "Awaiting approval", value: count("REQUESTED"), tone: count("REQUESTED") ? "warn" : "default" },
          { label: "Approved, to collect", value: count("APPROVED") },
          { label: "In transit", value: count("IN_TRANSIT"), tone: "info" },
          { label: "Discrepancies", value: count("RECEIVED_WITH_DISCREPANCY"), tone: count("RECEIVED_WITH_DISCREPANCY") ? "danger" : "default" },
          { label: "Replacements owed", value: owed, hint: "Supplying dealers awaiting stock" },
        ]} />
      )}
      {status === "open" && (
        <div className="mb-3">
          <QuickFilters value={qf} onChange={setQf} options={[
            { id: "all", label: "All open", count: data?.length }, { id: "REQUESTED", label: "Requested", count: count("REQUESTED") },
            { id: "APPROVED", label: "Approved", count: count("APPROVED") }, { id: "IN_TRANSIT", label: "In transit", count: count("IN_TRANSIT") },
            { id: "RECEIVED_WITH_DISCREPANCY", label: "Discrepancy", count: count("RECEIVED_WITH_DISCREPANCY") },
          ]} />
        </div>
      )}
      <Card padded={false}>
        <TransfersTable rows={rows} filterCount={status !== "open" ? 1 : 0} onClearFilters={() => { setStatus("open"); setQf("all"); }} filters={
          <FilterField label="Status" className="w-56"><Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setQf("all"); }}
            options={[{ value: "open", label: "Open transfers" }, { value: "all", label: "All transfers" }, ...["REQUESTED", "APPROVED", "IN_TRANSIT", "RECEIVED_WITH_DISCREPANCY", "COMPLETED", "CANCELLED", "REJECTED"].map((s) => ({ value: s, label: humanize(s) }))]} /></FilterField>
        } />
      </Card>
    </>
  );
}
