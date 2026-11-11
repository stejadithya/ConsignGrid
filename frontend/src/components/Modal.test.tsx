import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Drawer, Modal } from "./ui";

// A blurred top bar (backdrop-filter) becomes the containing block for position:fixed children, so a dialog
// rendered inside it would be trapped in the bar. Dialogs must therefore render into document.body.
afterEach(cleanup);

describe("Modal and Drawer", () => {
  it("render into document.body, not inside a backdrop-filter ancestor", () => {
    render(
      <header data-testid="bar" style={{ backdropFilter: "blur(8px)" }}>
        <Modal open title="Change your password" onClose={() => {}}><input aria-label="Current password" /></Modal>
      </header>,
    );
    const dialog = screen.getByRole("dialog", { name: "Change your password" });
    expect(screen.getByTestId("bar").contains(dialog)).toBe(false);
    expect(dialog.closest("body")).toBe(document.body);
    expect(dialog.parentElement?.parentElement).toBe(document.body);
  });

  it("drawers do the same, and nothing renders while closed", () => {
    const { rerender } = render(
      <header data-testid="bar" style={{ backdropFilter: "blur(8px)" }}>
        <Drawer open={false} title="Sale" onClose={() => {}}>x</Drawer>
      </header>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(
      <header data-testid="bar" style={{ backdropFilter: "blur(8px)" }}>
        <Drawer open title="Sale" onClose={() => {}}>x</Drawer>
      </header>,
    );
    expect(screen.getByTestId("bar").contains(screen.getByRole("dialog", { name: "Sale" }))).toBe(false);
  });
});
