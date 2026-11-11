import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { OperationalLoop } from "./OperationalLoop";

afterEach(() => cleanup());

describe("OperationalLoop", () => {
  it("is an ordered list of the four steps that ends back at the warehouse", () => {
    render(<OperationalLoop />);
    const list = screen.getByRole("list", { name: /keeps stock moving/ });
    expect(list.tagName).toBe("OL");
    const items = within(list).getAllByRole("listitem");
    expect(items.map((i) => i.querySelector(".text-label")?.textContent)).toEqual(["Warehouse", "Dealer", "Sale", "Replenishment"]);
    expect(items[3].textContent).toContain("then back to the warehouse");
    expect(items[3].textContent).toContain("automated by");
  });

  it("marks only Replenishment in yellow and keeps the arrows out of the accessibility tree", () => {
    const { container } = render(<OperationalLoop />);
    expect(container.querySelectorAll(".bg-brand")).toHaveLength(1);
    expect(within(screen.getAllByRole("listitem")[3]).getByText("Replenishment").closest("li")?.querySelector(".bg-brand")).toBeTruthy();
    container.querySelectorAll("svg").forEach((svg) => expect(svg.closest("[aria-hidden]") ?? svg.getAttribute("aria-hidden")).toBeTruthy());
    expect(screen.getByText("Back to the warehouse").closest("[aria-hidden]")).toBeTruthy();
  });
});
