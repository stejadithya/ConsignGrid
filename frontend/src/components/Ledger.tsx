"use client";

import { useMemo } from "react";
import { useProductIndex, useReference } from "@/components/pickers";
import { fmtDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { InventoryTransaction, Location } from "@/lib/types";
import { DataTable } from "./ui";

/** Recent ledger transactions filtered by location / product / reference. */
export function LedgerTable({ query }: { query: Record<string, string | number | undefined> }) {
  const { data } = useApi<InventoryTransaction[]>("/inventory/transactions", { limit: 200, ...query });
  const index = useProductIndex();
  const locations = useReference<Location[]>("/locations");
  const sku = useMemo(() => new Map([...index.byId.values()].map((p) => [p.id, `${p.display_name} (${p.sku})`])), [index]);
  const loc = useMemo(() => new Map((locations ?? []).map((l) => [l.id, l.code])), [locations]);
  return (
    <DataTable rows={data} rowKey={(t) => t.id} searchPlaceholder="Search transactions…" label="Stock movements"
      columns={[
        { key: "n", header: "Txn", pin: true, value: (t) => t.number, cell: (t) => <span className="sku text-label">{t.number}</span> },
        { key: "d", header: "When", value: (t) => t.occurred_at, cell: (t) => <span className="whitespace-nowrap">{fmtDateTime(t.occurred_at)}</span> },
        { key: "t", header: "Type", value: (t) => t.txn_type, cell: (t) => humanize(t.txn_type) },
        { key: "r", header: "Reference", value: (t) => t.reference_number, cell: (t) => t.reference_number ?? "—" },
        { key: "e", header: "Movements", cell: (t) => (
          <ul className="space-y-0.5 text-caption">
            {t.entries.map((e) => (
              <li key={e.id} className="num">
                <span className={e.quantity > 0 ? "text-success" : "text-danger"}>{e.quantity > 0 ? "+" : ""}{e.quantity}</span>{" "}
                {sku.get(e.product_id) ?? e.product_id} @ {loc.get(e.location_id) ?? e.location_id}
                {e.bucket !== "ON_HAND" && <span className="text-ink-muted"> ({humanize(e.bucket)})</span>}
              </li>
            ))}
          </ul>) },
        { key: "why", header: "Reason / notes", className: "min-w-64 whitespace-normal", value: (t) => `${t.reason ?? ""} ${t.notes ?? ""}`, cell: (t) => <span className="text-caption text-ink-secondary">{t.reason ?? t.notes ?? ""}</span> },
      ]} />
  );
}
