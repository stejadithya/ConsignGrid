import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InitialStockEntry } from "@/lib/types";
import { CorrectInitialStockModal } from "./InitialStockCorrection";

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const entry: InitialStockEntry = {
  transaction_id: 41, transaction_number: "TXN-000041", recorded_at: "2026-10-28T09:00:00Z", recorded_by: "Morgan Manager",
  location_id: 7, location_code: "AKT-AUC-001-01", location_name: "Main shop",
  lines: [{ product_id: 1, sku: "103294", name: "CEAT EcoDrive 195/65R15 91H", recorded: 12, current: 12, free_now: 9 }],
  corrections: [], can_correct: true, locked_reason: null, correctable_until: "2026-11-27T09:00:00Z",
};

describe("CorrectInitialStockModal", () => {
  it("won't go below what is sold or reserved, needs a reason, and sends only the changed tyres", async () => {
    const fetch = vi.fn(async () => reply({ transaction_id: 50, transaction_number: "TXN-000050" }, 201));
    vi.stubGlobal("fetch", fetch);
    const done = vi.fn();
    render(<CorrectInitialStockModal resellerId={3} entry={entry} onClose={() => {}} onDone={done} />);
    const box = screen.getByLabelText("Correct quantity for 103294");
    const save = () => screen.getByRole("button", { name: /^Save correction/ });

    // 3 of the 12 are sold or reserved: 2 is too low.
    fireEvent.change(box, { target: { value: "2" } });
    expect(screen.getByText("At least 3")).toBeTruthy();
    expect((save() as HTMLButtonElement).disabled).toBe(true);

    // The right figure, but no reason yet.
    fireEvent.change(box, { target: { value: "3" } });
    expect(screen.getByText(/103294 12 → 3/)).toBeTruthy();
    expect((save() as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText(/What was wrong\?/), { target: { value: "Typed 12 instead of 3" } });
    expect((save() as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(save());
    await waitFor(() => expect(done).toHaveBeenCalled());
    const [url, init] = fetch.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toContain("/resellers/3/initial-stock/41/corrections");
    expect(JSON.parse(String(init.body))).toEqual({ lines: [{ product_id: 1, quantity: 3 }], reason: "Typed 12 instead of 3" });
  });
});
