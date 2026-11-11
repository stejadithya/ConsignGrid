"use client";

import { CalendarClock, ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { ShopLabel } from "./pickers";
import { Alert, Badge, Button, ButtonLink, Card, DataTable, Field, Input, Modal, Textarea } from "./ui";

/** One dealer shop's next stock check (GET /stocktakes/schedule). */
export interface StockCheckRow {
  location_id: number; location_code: string; shop_name: string; city: string | null;
  reseller_id: number; reseller_name: string; sales_rep_user_id: number | null; sales_rep_name: string | null;
  last_count_on: string | null; due_on: string; status: "OVERDUE" | "DUE" | "SOON" | "OK"; days_overdue: number;
  moved_to: string | null; moved_reason: string | null; moved_by: string | null;
}

const MOVE_DAYS = 14;
const STATUS: Record<StockCheckRow["status"], { value: string; label: string }> = {
  OVERDUE: { value: "OVERDUE", label: "Overdue" }, DUE: { value: "HIGH", label: "Due today" },
  SOON: { value: "OPEN", label: "Due soon" }, OK: { value: "ACTIVE", label: "On track" },
};
const iso = (d: Date) => d.toISOString().slice(0, 10);

export function useStockCheckSchedule(resellerId?: number) {
  return useApi<StockCheckRow[]>("/stocktakes/schedule", resellerId ? { reseller_id: resellerId } : undefined);
}

/** Stock checks to do: overdue, due today and due soon (or every shop with all=true), each with Start and Move.
 *  A due check can be moved up to 14 days ahead with a reason; the Warehouse and Relationship Managers are told. */
export function StockCheckSchedule({ title = "Stock checks", resellerId, repId, all = false, canRecord }: {
  title?: string; resellerId?: number; repId?: number | null; all?: boolean; canRecord: boolean;
}) {
  const { data, error, reload } = useStockCheckSchedule(resellerId);
  const [moving, setMoving] = useState<StockCheckRow | null>(null);
  const rows = (data ?? []).filter((r) => (repId == null || r.sales_rep_user_id === repId) && (all || r.status !== "OK"))
    .sort((a, b) => a.due_on.localeCompare(b.due_on));
  return (
    <>
      <Alert>{error}</Alert>
      <Card padded={false} icon={CalendarClock} title={title}
        subtitle={data ? `${rows.filter((r) => r.status === "OVERDUE").length} overdue · ${rows.filter((r) => r.status === "DUE").length} due today · every 30 days` : undefined}>
        <DataTable mobile="cards" label={title} search={rows.length > 10} rows={data ? rows : undefined} rowKey={(r) => r.location_id}
          empty="No stock checks due" emptyHint="Each dealer shop is due a stock check 30 days after its last one."
          columns={[
            { key: "d", mobile: "primary", header: "Dealer", value: (r) => r.reseller_name,
              cell: (r) => <ShopLabel locationId={r.location_id} code={r.location_code} dealer={resellerId ? null : r.reseller_name} withDealer={!resellerId} /> },
            { key: "s", mobile: "status", header: "Status", cell: (r) => <Badge value={STATUS[r.status].value} label={r.status === "OVERDUE" ? `Overdue ${r.days_overdue}d` : STATUS[r.status].label} /> },
            { key: "due", mobile: "field", mobileOrder: 1, header: "Due", value: (r) => r.due_on, cell: (r) => (
              <div>{fmtDate(r.due_on)}{r.moved_to && <div className="text-caption text-ink-muted">Moved by {r.moved_by}: {r.moved_reason}</div>}</div>) },
            { key: "last", mobile: "field", mobileOrder: 2, header: "Last check", cell: (r) => r.last_count_on ? fmtDate(r.last_count_on) : "Never" },
            ...(resellerId ? [] : [{ key: "rep", header: "Sales rep", cell: (r: StockCheckRow) => r.sales_rep_name ?? "—" }]),
            ...(canRecord ? [{ key: "a", mobile: "action" as const, header: <span className="sr-only">Actions</span>, cell: (r: StockCheckRow) => (
              <div className="flex justify-end gap-2">
                <ButtonLink size="sm" href={`/stocktakes/new?location=${r.location_id}`}><ClipboardCheck aria-hidden />Start<span className="sr-only"> stock check at {r.reseller_name}</span></ButtonLink>
                <Button size="sm" variant="ghost" onClick={() => setMoving(r)}>Move<span className="sr-only"> stock check at {r.reseller_name}</span></Button>
              </div>) }] : []),
          ]} />
      </Card>
      {moving && <MoveStockCheck row={moving} onClose={() => setMoving(null)} onDone={() => { setMoving(null); reload(); }} />}
    </>
  );
}

/** Move a stock check to another day, up to 14 days ahead, with a reason. */
export function MoveStockCheck({ row, onClose, onDone }: { row: StockCheckRow; onClose: () => void; onDone: () => void }) {
  const today = new Date();
  const max = iso(new Date(today.getTime() + MOVE_DAYS * 864e5));
  const [date, setDate] = useState(iso(new Date(today.getTime() + 7 * 864e5)));
  const [reason, setReason] = useState("");
  const action = useAction();
  const ok = date >= iso(today) && date <= max && reason.trim().length >= 3;
  return (
    <Modal open title={`Move stock check: ${row.reseller_name}`} onClose={onClose}
      description={`Due ${fmtDate(row.due_on)}. Choose a day up to ${MOVE_DAYS} days ahead; the Warehouse and Relationship Managers are told.`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!ok || action.busy}
          onClick={async () => { if (await action.run(() => api.post(`/stocktakes/schedule/${row.location_id}/reschedule`, { date, reason: reason.trim() }))) onDone(); }}>
          {action.busy ? "Saving…" : "Move stock check"}</Button></>}>
      <Alert>{action.error}</Alert>
      <Field label="New date" required hint={`Today to ${fmtDate(max)}.`}>
        {(id) => <Input id={id} type="date" min={iso(today)} max={max} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <Field label="Why can't it happen on time?" required>
        {(id) => <Textarea id={id} rows={2} value={reason} placeholder="e.g. Owner away until Thursday" onChange={(e) => setReason(e.target.value)} />}
      </Field>
    </Modal>
  );
}
