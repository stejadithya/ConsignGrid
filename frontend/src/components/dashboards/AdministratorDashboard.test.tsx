import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdministratorDashboard } from "./AdministratorDashboard";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { id: 1, full_name: "SuperAdmin", role: "ADMINISTRATOR", reseller_id: null }, can: () => false }),
}));

const products = Array.from({ length: 40 }, (_, i) => ({ id: i + 1, sku: `SKU-${i + 1}`, is_active: true }));
const dashboard = {
  warehouse: { available: 400, on_hand: 400, reserved: 0 },
  backorders: { qty_awaiting_supply: 0, requests: 0 },
  sales_awaiting_invoicing: { qty: 0 },
};
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: string) => {
    const url = new URL(input, "http://localhost");
    if (url.pathname === "/api/products") {
      // The API caps the products list at 1000 and refuses anything larger (422), as GET /products does.
      return Number(url.searchParams.get("limit") ?? 200) > 1000 ? reply({ detail: "limit too large" }, 422) : reply(products);
    }
    if (url.pathname === "/api/reports/dashboard") return reply(dashboard);
    return reply(url.pathname.endsWith("/summary") ? {} : []);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AdministratorDashboard", () => {
  it("counts products the same way as the Products page", async () => {
    render(<AdministratorDashboard />);
    await waitFor(() => expect(screen.getByText("40 active")).toBeTruthy());
    const tile = screen.getByText("Products").closest("a");
    expect(tile?.textContent).toContain("40");
  });
});
