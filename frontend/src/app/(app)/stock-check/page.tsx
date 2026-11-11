"use client";

import { CheckStockPanel } from "@/components/CheckStock";
import { Alert, Card, PageHeader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useSearchParams } from "next/navigation";

/** Check Stock: which dealers (and the warehouse) hold a tyre, and how many. */
export default function StockCheckPage() {
  const { can } = useAuth();
  const product = useSearchParams().get("product_id");
  return (
    <>
      <PageHeader eyebrow="Inventory" title="Check stock"
        subtitle="Pick a tyre to see how many the warehouse has and which dealers hold it. Useful before a transfer, when a dealer asks, or before a stock check." />
      {can("transfer.request") ? <Card><CheckStockPanel initialProduct={product ? Number(product) : undefined} /></Card> : <Alert>This page is for dealership staff.</Alert>}
    </>
  );
}
