/**
 * The record-sale journey (finding 25): one sale, two tracks. Stock: recorded → replacement raised → shipped →
 * delivered. Billing: not invoiced → invoice record → invoiced in Xero. Plus the next step for whoever is looking.
 * What each viewer sees of billing follows D12 (the API already leaves out what they may not see).
 */
import type { Step } from "@/components/flow";
import type { Sale, SaleLine } from "./types";

export type BillingState = "NOT_INVOICED" | "INVOICE_DRAFTED" | "INVOICED";

const chargeable = (s: Sale) => s.lines.filter((l) => l.chargeable_qty > 0);
const lineState = (l: SaleLine): BillingState => l.invoice_state ?? (l.invoice_status === "INVOICED" ? "INVOICED" : l.invoice_status === "DRAFTED" ? "INVOICE_DRAFTED" : "NOT_INVOICED");
const uniq = (xs: (string | null | undefined)[]) => [...new Set(xs.filter((x): x is string => !!x))];

/** The sale's overall billing state: invoiced only when every chargeable line is. */
export function billingState(s: Sale): BillingState | null {
  const lines = chargeable(s);
  if (!lines.length) return null;
  if (lines.every((l) => lineState(l) === "INVOICED")) return "INVOICED";
  if (lines.some((l) => lineState(l) !== "NOT_INVOICED")) return "INVOICE_DRAFTED";
  return "NOT_INVOICED";
}

export const BILLING_LABEL: Record<BillingState, string> = { INVOICED: "Yes", INVOICE_DRAFTED: "Draft", NOT_INVOICED: "Not yet" };

const REPLACEMENT_LABEL: Record<string, string> = {
  OPEN: "Waiting for stock", PARTIALLY_FULFILLED: "Partly delivered", ALLOCATED: "Being packed", IN_TRANSIT: "On its way",
  FULFILLED: "Delivered", CANCELLED: "Cancelled",
};
const ORDER = ["OPEN", "PARTIALLY_FULFILLED", "ALLOCATED", "IN_TRANSIT", "FULFILLED", "CANCELLED"];

/** One word for the list: the least advanced replacement, or why there is none. */
export function replacementLabel(s: Sale): string {
  if (s.source === "CASH_SALE") return "Not needed";
  const reqs = s.lines.flatMap((l) => l.replenishment);
  if (!reqs.length) return "None";
  const worst = reqs.map((r) => r.status).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))[0];
  return REPLACEMENT_LABEL[worst] ?? worst;
}

export function stockTrack(s: Sale): Step[] {
  const recorded: Step = { label: "Sale recorded", state: "done", at: s.recorded_at, by: s.recorded_by, note: saleSourceLabel(s.source) };
  if (s.source === "CASH_SALE") {
    return [recorded, { label: "No replacement", state: "done", note: "Sold from the warehouse, so nothing needs replacing" }];
  }
  const reqs = s.lines.flatMap((l) => l.replenishment).filter((r) => r.status !== "CANCELLED");
  if (!reqs.length) {
    return [recorded, { label: "No replacement raised", state: "done", note: "The agreed stock level is already covered, or auto-replenish is off" }];
  }
  const deliveries = reqs.flatMap((r) => r.deliveries ?? []);
  const shipped = deliveries.length > 0;
  const delivered = reqs.every((r) => r.status === "FULFILLED");
  const received = deliveries.filter((d) => d.received_at);
  return [
    recorded,
    { label: "Replacement raised", state: "done", note: uniq(reqs.map((r) => r.number)).join(", ") },
    { label: "Replacement shipped", state: shipped ? "done" : "current", at: deliveries[0]?.dispatched_at, note: uniq(deliveries.map((d) => d.number)).join(", ") || undefined },
    { label: "Replacement delivered", state: delivered ? "done" : shipped ? "current" : "pending", at: delivered ? received[received.length - 1]?.received_at : undefined },
  ];
}

/** Full billing track for RM/FM/Admin and the dealer; others see only invoiced yes / not yet (see `billingState`). */
export function billingTrack(s: Sale): Step[] {
  const state = billingState(s);
  const lines = chargeable(s);
  const records = uniq(lines.map((l) => l.invoice_number));
  const xero = uniq(lines.map((l) => l.xero_reference));
  const at = lines.map((l) => l.invoiced_at).filter(Boolean).sort().pop();
  return [
    { label: "Sold, not invoiced", state: "done", at: s.recorded_at },
    { label: "Invoice record created", state: state === "NOT_INVOICED" ? "current" : "done", note: records.join(", ") || undefined },
    { label: "Invoiced in Xero", state: state === "INVOICED" ? "done" : state === "INVOICE_DRAFTED" ? "current" : "pending", at,
      note: xero.length ? `Xero no. ${xero.join(", ")}` : undefined },
  ];
}

/** What the person looking at the sale should do next, if anything. */
export function nextStep(s: Sale, can: (permission: string) => boolean, isDealer: boolean): string | null {
  const state = billingState(s);
  const reqs = s.lines.flatMap((l) => l.replenishment).filter((r) => r.status !== "CANCELLED");
  if (can("invoice.create") && state === "NOT_INVOICED") return "Create invoice record";
  if (can("invoice.create") && state === "INVOICE_DRAFTED") return "Mark as invoiced in Xero";
  if (can("replenishment.dispatch") && reqs.some((r) => r.status === "ALLOCATED")) return "Pick & dispatch the replacement";
  if (can("replenishment.approve") && reqs.some((r) => ["OPEN", "PARTIALLY_FULFILLED"].includes(r.status))) return "Reserve stock for the replacement";
  if ((isDealer || can("delivery.confirm")) && reqs.some((r) => r.status === "IN_TRANSIT")) return "Confirm the replacement when it arrives";
  return null;
}

/** How a sale was recorded, in plain words. CASH_SALE is shown as a non-consignment sale (D6; the code stays). */
export function saleSourceLabel(source: string) {
  return { RESELLER_REPORT: "Reported by the dealer", REP_VISIT: "Sales rep visit", STOCKTAKE: "Found in a stock check",
    CASH_SALE: NON_CONSIGNMENT_LABEL, OTHER: "Other" }[source] ?? source;
}

export const NON_CONSIGNMENT_LABEL = "Non-consignment sale (from warehouse)";
