import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DealerHistoryTab } from "./DealerHistory";

const reply = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("DealerHistoryTab", () => {
  it("answers the six questions for an existing dealer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({
      reseller_id: 3, onboarded_at: "2026-03-02T09:00:00Z", onboarded_by: "Morgan Manager", dealer_type: "EXISTING",
      first_stock: { occurred_at: "2026-03-02T10:00:00Z", transaction_number: "TXN-1", txn_type: "OPENING_BALANCE", reference_number: null },
      onboarding_stock_kind: "INITIAL_STOCK", onboarding_stock_at: "2026-03-02T10:00:00Z",
      onboarding_stock: [{ product_id: 1, sku: "103294", name: "CEAT EcoDrive 195/65R15 91H", quantity: 6 }],
      units_sold: 42, sales_count: 17, last_sale: { id: 9, number: "SAL-000117", sale_date: "2026-10-20", units: 2 },
    })));
    render(<DealerHistoryTab resellerId={3} />);
    expect(await screen.findByText("Existing dealer (joined with stock)")).toBeTruthy();
    expect(screen.getByText("Added by Morgan Manager")).toBeTruthy();
    expect(screen.getByText(/Initial stock loaded$/)).toBeTruthy();                       // first consignment
    expect(screen.getByText("42 in 17 sales")).toBeTruthy();
    expect(screen.getByRole("link", { name: "SAL-000117" }).getAttribute("href")).toBe("/sales?sale=9");
    expect(screen.getByText("Onboarded with this stock")).toBeTruthy();
    expect(screen.getAllByText("CEAT EcoDrive 195/65R15 91H").length).toBeGreaterThan(0);
  });

  it("explains a new dealer with no stock or sales yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({
      reseller_id: 4, onboarded_at: "2026-10-01T09:00:00Z", onboarded_by: null, dealer_type: "NEW", first_stock: null,
      onboarding_stock_kind: null, onboarding_stock_at: null, onboarding_stock: [], units_sold: 0, sales_count: 0, last_sale: null,
    })));
    render(<DealerHistoryTab resellerId={4} />);
    expect(await screen.findByText("New dealer")).toBeTruthy();
    expect(screen.getByText("No stock has reached this dealer yet")).toBeTruthy();
    expect(screen.getByText("No sales yet")).toBeTruthy();
  });
});
