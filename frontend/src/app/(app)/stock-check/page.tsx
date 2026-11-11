"use client";

import { CheckStockPanel } from "@/components/CheckStock";
import { Alert, Card, PageHeader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useSearchParams } from "next/navigation";
import { vocab } from "@/lib/terms";
import { branding } from "@/config/branding";

/** Check Stock: which dealers (and the warehouse) hold a tyre, and how many. */
export default function StockCheckPage() {
  const { can } = useAuth();
  const product = useSearchParams().get("product_id");
  return (
    <>
      <PageHeader eyebrow="Inventory" title="Check stock"
        subtitle={`Pick ${vocab.aItem} to see how many the warehouse has and which ${vocab.partners} hold it. Useful before a transfer, when ${vocab.aPartner} asks, or before a stock check.`} />
      {can("transfer.request") ? <Card><CheckStockPanel initialProduct={product ? Number(product) : undefined} /></Card> : <Alert>This page is for {branding.companyName} staff.</Alert>}
    </>
  );
}
