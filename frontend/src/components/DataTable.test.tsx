import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Badge, DataTable, TableCheckbox, type Column } from "./ui";

interface Row { id: number; sku: string; name: string; qty: number; active: boolean }
const rows: Row[] = [{ id: 1, sku: "103294", name: "CEAT EcoDrive", qty: 4, active: true }, { id: 2, sku: "103671", name: "CEAT Milaze", qty: 0, active: false }];
const columns: Column<Row>[] = [
  { key: "n", header: "Product", value: (r) => r.name, cell: (r) => r.name },
  { key: "s", header: "SKU", mobile: "secondary", cell: (r) => r.sku },
  { key: "q", header: "Warehouse", numeric: true, mobile: "field", mobileLabel: "In warehouse", value: (r) => r.qty, cell: (r) => r.qty },
  { key: "st", header: "Status", mobile: "status", cell: (r) => <Badge value={r.active ? "ACTIVE" : "CLOSED"} label={r.active ? "Active" : "Inactive"} /> },
  { key: "a", header: <span className="sr-only">Actions</span>, mobile: "action", cell: (r) => <button type="button" aria-label={`Edit ${r.sku}`}>Edit</button> },
];

afterEach(() => cleanup());

describe("DataTable card mode", () => {
  it("is one table with explicit roles: rows, cells and the column headers screen readers use", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={columns} mobile="cards" label="Products" search={false} />);
    const table = screen.getByRole("table", { name: "Products" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Product", "SKU", "Warehouse", "Status", "Actions"]);
    expect(within(table).getAllByRole("row")).toHaveLength(3);                       // header + 2 rows, rendered once
    expect(screen.getAllByText("CEAT EcoDrive")).toHaveLength(1);                    // no duplicate desktop/mobile copy
    expect(screen.getByRole("button", { name: "Edit 103294" })).toBeTruthy();
  });

  it("draws card labels from data-label, adding no text to the cell (screen readers keep the column header)", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={columns} mobile="cards" search={false} />);
    const cells = screen.getAllByRole("cell").filter((c) => c.getAttribute("data-label") === "In warehouse");
    expect(cells).toHaveLength(2);
    expect(cells.map((c) => c.textContent)).toEqual(["4", "0"]);
    expect(screen.queryByText("In warehouse")).toBeNull();
  });

  it("announces the sort state on the column header", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={columns} mobile="cards" search={false} />);
    const header = screen.getByRole("columnheader", { name: /Warehouse/ });
    expect(header.getAttribute("aria-sort")).toBeNull();
    fireEvent.click(within(header).getByRole("button"));
    expect(header.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(within(header).getByRole("button"));
    expect(header.getAttribute("aria-sort")).toBe("descending");
  });

  it("keeps the default (scroll) table free of the card-only roles and labels", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={columns} search={false} />);
    expect(screen.queryByText("In warehouse")).toBeNull();
    expect(screen.getByRole("table")).toBeTruthy();
  });
});

describe("TableCheckbox", () => {
  it("keeps its label associated with the checkbox", () => {
    let checked = false;
    render(<TableCheckbox label="Select SAL-000001 103294" checked={checked} onChange={() => { checked = !checked; }} />);
    const box = screen.getByRole("checkbox", { name: "Select SAL-000001 103294" });
    fireEvent.click(box);
    expect(checked).toBe(true);
  });
});
