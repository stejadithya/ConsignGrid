import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CheckStockPanel } from "./CheckStock";

const product = { id: 7, sku: "103671", display_name: "CEAT EcoDrive 175/65R14 82T", size_display: "175/65R14" };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url.includes("/api/products") ? [product]
      : url.includes("/api/transfers/sources") ? { product_id: 7, warehouse_available: 12, sources: [] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("CheckStockPanel", () => {
  it("starts empty and calls the API only when Search is pressed", async () => {
    render(<CheckStockPanel />);
    const box = screen.getByLabelText(/Tyre/);
    expect((box as HTMLInputElement).value).toBe("");
    fireEvent.change(box, { target: { value: "1036" } });
    fireEvent.change(box, { target: { value: "103671" } });
    await new Promise((r) => setTimeout(r, 50));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("Main warehouse · available")).toBeTruthy());
    const urls = vi.mocked(fetch).mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toContain("/api/products?q=103671");
    expect(urls.some((u) => u.includes("/api/transfers/sources?product_id=7"))).toBe(true);
  });

  it("searches as you type once 3 or more characters are entered and typing pauses", async () => {
    render(<CheckStockPanel />);
    const box = screen.getByLabelText(/Tyre/);
    fireEvent.change(box, { target: { value: "17" } });
    await new Promise((r) => setTimeout(r, 400));
    expect(fetch).not.toHaveBeenCalled();                                    // fewer than 3 characters: nothing yet
    fireEvent.change(box, { target: { value: "175 6" } });
    fireEvent.change(box, { target: { value: "175 65" } });
    await waitFor(() => expect(screen.getByText("Main warehouse · available")).toBeTruthy());
    const searches = vi.mocked(fetch).mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/api/products"));
    expect(searches).toEqual([expect.stringContaining("q=175+65")]);           // one search, after the pause
  });

  it("says when nothing matches", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
    render(<CheckStockPanel />);
    fireEvent.change(screen.getByLabelText(/Tyre/), { target: { value: "nothing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/No tyre matches/)).toBeTruthy());
  });
});
