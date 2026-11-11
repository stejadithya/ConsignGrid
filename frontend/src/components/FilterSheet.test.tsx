import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable, FilterField, Input, QuickFilters, type Column } from "./ui";

interface Row { id: number; name: string; qty: number }
const rows: Row[] = [{ id: 1, name: "Alpha", qty: 2 }, { id: 2, name: "Charlie", qty: 9 }, { id: 3, name: "Bravo", qty: 5 }];
const columns: Column<Row>[] = [
  { key: "n", header: "Tyre", mobileSort: "Name", value: (r) => r.name, cell: (r) => r.name },
  { key: "q", header: "Qty", numeric: true, mobile: "field", mobileSort: true, value: (r) => r.qty, cell: (r) => r.qty },
  { key: "x", header: "Hidden from Sort by", value: (r) => r.id, cell: (r) => r.id },
];

function Table() {
  const [size, setSize] = useState("");
  return (
    <DataTable mobile="cards" label="Tyres" rows={rows.filter((r) => r.name.includes(size))} rowKey={(r) => r.id} columns={columns}
      quickFilters={<QuickFilters value="all" onChange={() => {}} options={[{ id: "all", label: "All" }, { id: "low", label: "Low" }]} />}
      filterCount={size ? 1 : 0} onClearFilters={() => setSize("")}
      filters={<FilterField label="Name contains" className="w-36"><Input aria-label="Name contains" value={size} onChange={(e) => setSize(e.target.value)} /></FilterField>} />
  );
}

const phone = (matches: boolean) => vi.stubGlobal("matchMedia", vi.fn((q: string) => ({
  matches: q.includes("40rem") ? matches : false, media: q, addEventListener: () => {}, removeEventListener: () => {},
})));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("DataTable filters on a phone", () => {
  beforeEach(() => phone(true));

  it("keeps search and quick filters in view and moves the other filters behind a Filters button", () => {
    render(<Table />);
    expect(screen.getByRole("searchbox", { name: "Search table" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Quick filters" })).toBeTruthy();
    expect(screen.queryByLabelText("Name contains")).toBeNull();
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
  });

  it("opens a sheet with visible labels, counts active filters and clears them", () => {
    render(<Table />);
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    const sheet = screen.getByRole("dialog", { name: "Filters and sort" });
    expect(within(sheet).getByText("Name contains", { selector: "div" })).toBeTruthy();   // the visible label
    fireEvent.change(within(sheet).getByLabelText("Name contains"), { target: { value: "Br" } });
    expect(within(sheet).getByRole("button", { name: "Apply (1 row)" })).toBeTruthy();
    fireEvent.click(within(sheet).getByRole("button", { name: "Apply (1 row)" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    const button = screen.getByRole("button", { name: /^Filters/ });
    expect(button.textContent).toBe("Filters (1)");
    fireEvent.click(button);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Clear all" }));
    expect(within(screen.getByRole("dialog")).getByLabelText<HTMLInputElement>("Name contains").value).toBe("");
  });

  it("offers only the chosen columns under Sort by, sorts, and announces the sort", () => {
    render(<Table />);
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    const sheet = screen.getByRole("dialog");
    const options = within(within(sheet).getByRole("group", { name: "Sort by" })).getAllByRole("radio").map((r) => r.parentElement?.textContent);
    expect(options).toEqual(["Default order", "Name", "Qty"]);
    fireEvent.click(within(sheet).getByRole("radio", { name: "Qty" }));
    fireEvent.click(within(sheet).getByRole("radio", { name: "Descending" }));
    fireEvent.click(within(sheet).getByRole("button", { name: /^Apply/ }));
    expect(screen.getByText("Sorted by Qty, descending").getAttribute("aria-live")).toBe("polite");
    const names = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
    expect(names).toEqual(["Charlie", "Bravo", "Alpha"]);
    expect(screen.getAllByRole("columnheader")[1].getAttribute("aria-sort")).toBe("descending");
  });

  it("closes with Escape", () => {
    render(<Table />);
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("DataTable filters on wider screens", () => {
  beforeEach(() => phone(false));

  it("shows the filters inline, with no Filters button and no extra label", () => {
    render(<Table />);
    expect(screen.getByLabelText("Name contains")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Filters/ })).toBeNull();
    expect(screen.queryByText("Name contains", { selector: "div" })).toBeNull();
  });
});
