"use client";

import Link from "next/link";
import { useState } from "react";
import { ResellerSelect, ShopLabel } from "@/components/pickers";
import { DealerSkuReport } from "@/components/DealerSkuReport";
import { StockCorrectionsReport } from "@/components/InitialStockCorrection";
import { ResellerHistory } from "@/components/ResellerHistory";
import { Alert, Badge, ButtonLink, Card, DataTable, Empty, Field, PageHeader, Qty, Tabs } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Row = Record<string, string | number | null>;

export default function ReportsPage() {
  const { user } = useAuth();
  const staff = !user?.reseller_id;
  const [tab, setTab] = useState("history");
  const [reseller, setReseller] = useState<number | "">(user?.reseller_id ?? "");
  return (
    <>
      <PageHeader title="Reports" subtitle="Mandatory: total consignment stock, outstanding backorders, dealer transaction history. Plus operational views."
        actions={<><ButtonLink href="/consignment">Total consignment stock</ButtonLink><ButtonLink href="/backorders">Outstanding backorders</ButtonLink></>} />
      <Tabs active={tab} onChange={setTab} tabs={[
        { id: "history", label: "Dealer transaction history" },
        { id: "dealer-sku", label: "By dealer by SKU" },
        ...(staff ? [{ id: "warehouse", label: "Warehouse availability" }, { id: "demand", label: "Demand by SKU" },
          { id: "uninvoiced", label: "Sold, not invoiced" }, { id: "ageing", label: "Consignment ageing" }] : []),
        { id: "stocktake", label: "Stocktake discrepancies" },
        ...(staff ? [{ id: "corrections", label: "Stock corrections" }] : []),
      ]} />
      {tab === "history" && (
        <>
          {staff && (
            <div className="mb-4 w-80">
              <Field label="Dealer">
                {(id) => <ResellerSelect id={id} value={reseller} onChange={setReseller} placeholder="Select a dealer" />}
              </Field>
            </div>
          )}
          {reseller ? <ResellerHistory resellerId={Number(reseller)} /> : <Card><Empty>Select a dealer to see its chronological ledger.</Empty></Card>}
        </>
      )}
      {tab === "dealer-sku" && <DealerSkuReport />}
      {tab === "corrections" && <StockCorrectionsReport />}
      {tab === "warehouse" && <Simple path="/reports/warehouse-availability" cols={[
        ["location_code", "Warehouse", "loc"], ["sku", "SKU"], ["product_name", "Product"], ["on_hand", "On hand", "n"], ["reserved", "Reserved", "n"],
        ["blocked", "Blocked", "n"], ["available", "Available", "n"], ["incoming", "Incoming (PO)", "n"], ["awaiting_supply_demand", "Backorder demand", "n"]]} />}
      {tab === "demand" && <Simple path="/reports/demand-by-sku" cols={[
        ["sku", "SKU"], ["requests", "Requests", "n"], ["outstanding", "Outstanding", "n"], ["sale", "Sale-driven", "n"], ["transfer", "Transfer-driven", "n"],
        ["allocated", "Allocated", "n"], ["in_transit", "In transit", "n"], ["awaiting_supply", "Awaiting supply", "n"], ["warehouse_available", "WH available", "n"],
        ["incoming", "Incoming", "n"], ["uncovered_after_incoming", "Uncovered after incoming", "n"]]} />}
      {tab === "uninvoiced" && <Simple path="/reports/uninvoiced-sales" cols={[
        ["reseller_name", "Dealer"], ["uninvoiced_qty", "Uninvoiced qty", "n"],
        ["on_draft_qty", "On an invoice record (not yet in Xero)", "n"], ["oldest_sale_date", "Oldest sale", "d"]]} />}
      {tab === "ageing" && <Simple path="/reports/consignment-ageing" cols={[
        ["location_code", "Dealer / shop", "loc"], ["sku", "SKU"], ["on_hand", "On hand", "n"], ["last_sale", "Last sale", "dt"], ["days_since_sale", "Days since sale", "n"],
        ["last_movement", "Last movement", "dt"]]} />}
      {tab === "stocktake" && <Simple path="/reports/stocktake-discrepancies" cols={[
        ["number", "Stocktake", "st"], ["count_date", "Date", "d"], ["reseller_name", "Dealer"], ["location_code", "Shop", "shop"], ["sku", "SKU"],
        ["expected_qty", "Expected", "n"], ["counted_qty", "Counted", "n"], ["variance", "Variance", "n"], ["qty_sold", "Sold", "n"], ["qty_missing", "Written off (before 1.11)", "n"], ["status", "Status", "b"]]} />}
    </>
  );
}

function Simple({ path, cols }: { path: string; cols: [string, string, string?][] }) {
  const { data, error } = useApi<Row[]>(path);
  return (
    <>
      <Alert>{error}</Alert>
      <Card padded={false}>
        <DataTable rows={data} rowKey={(r) => JSON.stringify(r)} pageSize={100} label="Report"
          columns={cols.map(([key, header, kind]) => ({
            key, header, align: kind === "n" ? "right" as const : undefined,
            value: (r: Row) => r[key],
            cell: (r: Row) => kind === "n" ? <Qty value={r[key] as number | null} />
              : kind === "d" ? fmtDate(r[key] as string) : kind === "dt" ? fmtDateTime(r[key] as string)
              : kind === "loc" ? <ShopLabel code={r[key] as string | null} />
              : kind === "shop" ? <ShopLabel code={r[key] as string | null} withDealer={false} />
              : kind === "b" ? <Badge value={r[key] as string} /> : kind === "st" ? <Link className="link" href={`/stocktakes/${r.stocktake_id}`}>{r[key]}</Link>
              : String(r[key] ?? "—"),
          }))} />
      </Card>
    </>
  );
}
