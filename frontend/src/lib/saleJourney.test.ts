import { describe, expect, it } from "vitest";
import { billingState, billingTrack, nextStep, replacementLabel, stockTrack } from "./saleJourney";
import type { Sale, SaleLine } from "./types";

const line = (patch: Partial<SaleLine> = {}): SaleLine => ({
  id: 1, product_id: 1, sku: "TYR-1", product_name: "Tyre", quantity: 2, reversed_qty: 0, chargeable_qty: 2, unit_price: "0.00",
  price_source: "NOT_PRICED", tax_code: "STD", tax_rate: "0", line_net: "0.00", invoice_status: "UNINVOICED", invoice_number: null,
  replenishment: [], ...patch,
});
const sale = (lines: SaleLine[], source = "RESELLER_REPORT"): Sale => ({
  id: 1, number: "SAL-1", reseller_id: 1, reseller_name: "Alpha", location_id: 1, location_code: "A-01", sale_date: "2026-10-01",
  source, source_reference: null, stocktake_id: null, recorded_by: "Dee", recorded_at: "2026-10-01T10:00:00Z", notes: null,
  total_qty: 2, total_net: "0.00", lines,
} as Sale);
const can = (...perms: string[]) => (p: string) => perms.includes(p);

describe("record-sale journey", () => {
  it("is invoiced only when every chargeable line is", () => {
    expect(billingState(sale([line()]))).toBe("NOT_INVOICED");
    expect(billingState(sale([line({ invoice_state: "INVOICED" }), line({ id: 2, invoice_state: "INVOICE_DRAFTED" })]))).toBe("INVOICE_DRAFTED");
    expect(billingState(sale([line({ invoice_state: "INVOICED" }), line({ id: 2, chargeable_qty: 0 })]))).toBe("INVOICED");
  });

  it("follows the replacement from raised to delivered", () => {
    const raised = sale([line({ replenishment: [{ id: 5, number: "REP-5", qty_required: 2, status: "ALLOCATED", deliveries: [] }] })]);
    expect(stockTrack(raised).map((s) => s.state)).toEqual(["done", "done", "current", "pending"]);
    expect(replacementLabel(raised)).toBe("Being packed");
    const done = sale([line({ replenishment: [{ id: 5, number: "REP-5", qty_required: 2, status: "FULFILLED",
      deliveries: [{ id: 9, number: "DEL-9", status: "RECEIVED", dispatched_at: "2026-10-02T00:00:00Z", received_at: "2026-10-03T00:00:00Z" }] }] })]);
    expect(stockTrack(done).map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
    expect(stockTrack(done)[2].note).toBe("DEL-9");
    expect(replacementLabel(sale([line()], "CASH_SALE"))).toBe("Not needed");
  });

  it("shows the Xero number in the billing track when the viewer may see it", () => {
    const steps = billingTrack(sale([line({ invoice_state: "INVOICED", invoice_number: "INV-1", xero_reference: "X-1", invoiced_at: "2026-10-04T00:00:00Z" })]));
    expect(steps.map((s) => s.state)).toEqual(["done", "done", "done"]);
    expect(steps[1].note).toBe("INV-1");
    expect(steps[2].note).toBe("Xero no. X-1");
  });

  it("gives each role its next step", () => {
    const s = sale([line({ replenishment: [{ id: 5, number: "REP-5", qty_required: 2, status: "ALLOCATED" }] })]);
    expect(nextStep(s, can("invoice.create", "replenishment.dispatch"), false)).toBe("Create invoice record");
    expect(nextStep(s, can("replenishment.dispatch"), false)).toBe("Pick & dispatch the replacement");
    expect(nextStep(sale([line({ replenishment: [{ id: 5, number: "REP-5", qty_required: 2, status: "IN_TRANSIT" }] })]), can(), true))
      .toBe("Confirm the replacement when it arrives");
    expect(nextStep(sale([line({ invoice_state: "INVOICED" })]), can("invoice.create"), false)).toBeNull();
  });
});
