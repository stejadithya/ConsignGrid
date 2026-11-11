import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog, DataTable } from "./ui";

vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

const rows = [
  { id: 1, sku: "TYR-001", qty: 5 },
  { id: 2, sku: "TYR-002", qty: 0 },
  { id: 3, sku: "ABC-100", qty: 12 },
];

describe("DataTable", () => {
  it("searches across columns and sorts", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={[
      { key: "sku", header: "SKU", value: (r) => r.sku, cell: (r) => r.sku },
      { key: "qty", header: "Qty", value: (r) => r.qty, cell: (r) => r.qty },
    ]} />);
    expect(screen.getByText("3 rows")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search table"), { target: { value: "tyr" } });
    expect(screen.getByText("2 rows")).toBeTruthy();
    expect(screen.queryByText("ABC-100")).toBeNull();
    fireEvent.change(screen.getByLabelText("Search table"), { target: { value: "" } });
    fireEvent.click(screen.getByText("Qty"));
    const cells = screen.getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(cells).toEqual(["TYR-0020", "TYR-0015", "ABC-10012"]);
  });

  it("shows the empty message", () => {
    render(<DataTable rows={[]} rowKey={() => 1} columns={[]} empty="Nothing here" search={false} />);
    expect(screen.getByText("Nothing here")).toBeTruthy();
  });
});

describe("ConfirmDialog", () => {
  it("requires a reason before confirming a high-impact action", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="Cancel backorder" requireReason danger onConfirm={onConfirm} onClose={() => {}} />);
    const confirm = screen.getByRole("button", { name: "Confirm" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Reseller closed the range" } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith("Reseller closed the range");
  });

  it("renders nothing when closed", () => {
    const { container } = render(<ConfirmDialog open={false} title="x" onConfirm={() => {}} onClose={() => {}} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("InfoTip", () => {
  it("opens on keyboard focus and closes with Escape", async () => {
    const { Field } = await import("./ui");
    render(<Field label="Account reference" info="Created automatically.">{(id) => <input id={id} />}</Field>);
    const tip = screen.getByRole("button", { name: "About Account reference" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.focus(tip);
    expect(screen.getByRole("tooltip").textContent).toBe("Created automatically.");
    fireEvent.keyDown(tip, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    // The label still names the input exactly.
    expect(screen.getByLabelText("Account reference")).toBeTruthy();
  });
});
