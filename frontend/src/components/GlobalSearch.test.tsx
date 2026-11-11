import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalSearch, type SearchResults } from "./GlobalSearch";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const reply = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); push.mockReset(); });

const results: SearchResults = {
  query: "SRQ-000002",
  documents: [
    { type: "STOCK_REQUEST", label: "Stock request", id: 2, title: "SRQ-000002", subtitle: "Roskill Tyres", status: "DELIVERED", when: "2026-11-02T09:00:00Z", href: "/stock-requests/2", exact: true },
    { type: "STOCK_REQUEST", label: "Stock request", id: 12, title: "SRQ-000012", subtitle: "Henderson Tyres", status: "SUBMITTED", when: "2026-11-03T09:00:00Z", href: "/stock-requests/12", exact: false },
  ],
  dealers: [{ type: "DEALER", label: "Dealer", id: 7, title: "Roskill Tyres", subtitle: "RSK-AUC-001", status: "ACTIVE", when: null, href: "/resellers/7", exact: false }],
  tyres: [], people: [],
};

describe("GlobalSearch", () => {
  it("searches from 3 characters, groups the results, and Enter opens an exact number", async () => {
    const fetch = vi.fn<(url: RequestInfo | URL) => Promise<Response>>(async () => reply(results));
    vi.stubGlobal("fetch", fetch);
    render(<GlobalSearch />);
    const box = screen.getAllByRole("combobox", { name: "Search everything" })[0];
    fireEvent.change(box, { target: { value: "sr" } });
    await new Promise((r) => setTimeout(r, 400));
    expect(fetch).not.toHaveBeenCalled();                      // under 3 characters: nothing sent

    fireEvent.change(box, { target: { value: "SRQ-000002" } });
    await waitFor(() => expect(screen.getByRole("listbox", { name: "Search results" })).toBeTruthy());
    expect(String(fetch.mock.calls[0][0])).toContain("/api/search?q=SRQ-000002");
    expect(screen.getByRole("group", { name: "Documents" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Dealers" })).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Tyres" })).toBeNull();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/stock-requests/2");
  });

  it("arrow keys move through every group and Enter opens the highlighted result", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(results)));
    render(<GlobalSearch />);
    const box = screen.getAllByRole("combobox", { name: "Search everything" })[0];
    fireEvent.change(box, { target: { value: "roskill" } });
    await waitFor(() => expect(screen.getByRole("listbox", { name: "Search results" })).toBeTruthy());
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowDown" });              // third result: the dealer
    expect(screen.getAllByRole("option")[2].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/resellers/7");
  });

  it("says so when nothing matches", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ query: "zzz", documents: [], dealers: [], tyres: [], people: [] })));
    render(<GlobalSearch />);
    fireEvent.change(screen.getAllByRole("combobox", { name: "Search everything" })[0], { target: { value: "zzz" } });
    expect(await screen.findByText(/Nothing found for “zzz”/)).toBeTruthy();
  });
});
