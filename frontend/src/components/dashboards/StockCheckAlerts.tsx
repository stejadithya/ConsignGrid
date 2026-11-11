"use client";

import { ClipboardX } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Stocktake } from "@/lib/types";
import { Badge, Card, cx, DataTable } from "../ui";

/** Stock checks with tyres not found that the dealer has not yet resolved (find window, finding 29). Hidden when none. */
export function StockCheckAlerts() {
  const { user } = useAuth();
  const { data } = useApi<Stocktake[]>("/stocktakes/awaiting-confirmation");
  if (!data?.length) return null;
  const isReseller = !!user?.reseller_id;
  const overdue = data.filter((s) => s.overdue).length;
  return (
    <Card padded={false} icon={ClipboardX}
      className={cx("mb-6", overdue ? "border-danger-line ring-2 ring-danger-line/60" : "border-warning-line")}
      title={isReseller ? "Action needed: tyres not found at a stock check" : "Stock checks awaiting dealer confirmation"}
      subtitle={`${data.length} stock check(s) with tyres not found${overdue ? ` — ${overdue} past the date` : ""}. Find them and ask for a re-check, or they are invoiced as sold on the date shown.`}>
      <DataTable mobile="cards" label="Stock checks waiting" search={false} rows={data} rowKey={(s) => s.id} pageSize={10}
        rowClassName={(s) => s.overdue && "bg-danger-soft/40"}
        columns={[
          { key: "n", mobile: "primary" as const, header: "Stock check", cell: (s) => <Link className="link font-medium" href={`/stocktakes/${s.id}`}>{s.number}</Link> },
          ...(isReseller ? [] : [{ key: "r", mobile: "secondary" as const, header: "Dealer", cell: (s: Stocktake) => <div><div>{s.reseller_name}</div><div className="text-caption text-ink-muted">{s.location_code}</div></div> }]),
          { key: "c", header: "Counted", cell: (s) => <span className="text-ink-secondary">{fmtDate(s.count_date)} · {s.counted_by}</span> },
          { key: "m", mobile: "field" as const, mobileOrder: 1, header: "Not found", align: "right", cell: (s) => <span className="num font-semibold text-danger">{s.total_shortage}</span> },
          { key: "d", mobile: "field" as const, mobileOrder: 2, header: "Invoiced on", cell: (s) => s.status === "AWAITING_RESELLER"
            ? <span className={s.overdue ? "font-medium text-danger" : "text-ink-secondary"}>{fmtDate(s.confirm_due_at)}</span>
            : <span className="text-ink-muted">Paused</span> },
          { key: "s", mobile: "status" as const, header: "Status", cell: (s) => s.status === "RECHECK_REQUESTED" ? <Badge value="UNDER_REVIEW" label="Re-check requested" />
            : s.status === "DISPUTED" ? <Badge value="OVERDUE" label="Disputed" />
            : s.overdue ? <Badge value="OVERDUE" label="Past the date" />
            : <Badge value="AWAITING_RESELLER" label="Awaiting dealer" /> },
        ]} />
    </Card>
  );
}
