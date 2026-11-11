import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tabs } from "./ui";

afterEach(() => cleanup());

describe("Tabs", () => {
  it("marks the selected tab clearly (bold, pale yellow tint, thick yellow underline) and tints others on hover and press", () => {
    const onChange = vi.fn();
    render(<Tabs active="b" onChange={onChange} tabs={[{ id: "a", label: "Overview" }, { id: "b", label: "Dealer history" }]} />);
    const selected = screen.getByRole("tab", { name: "Dealer history" });
    expect(selected.getAttribute("aria-selected")).toBe("true");
    expect(selected.className).toMatch(/bg-brand-soft/);
    expect(selected.className).toMatch(/font-semibold/);
    expect(selected.className).toMatch(/border-brand/);
    const other = screen.getByRole("tab", { name: "Overview" });
    expect(other.className).toMatch(/hover:bg-neutral-soft/);
    expect(other.className).toMatch(/active:bg-line/);
    fireEvent.click(other);
    expect(onChange).toHaveBeenCalledWith("a");
  });
});
