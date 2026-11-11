import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button, MobileActionBar, MoreMenu, PageHeader } from "./ui";

afterEach(() => cleanup());

const items = (onEdit = vi.fn(), onCancel = vi.fn()) => [
  { label: "Cancel request", danger: true, onSelect: onCancel },
  { label: "Print pick sheet", href: "/print" },
  { label: "Edit", onSelect: onEdit },
];

describe("MoreMenu", () => {
  it("is a labelled button that opens a menu, focuses the first item and lists destructive actions last", () => {
    render(<MoreMenu items={items()} />);
    const trigger = screen.getByRole("button", { name: "More actions" });
    expect(trigger.textContent).toBe("More");                                       // never icon-only
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const entries = screen.getAllByRole("menuitem");
    expect(entries.map((e) => e.textContent)).toEqual(["Print pick sheet", "Edit", "Cancel request"]);
    expect(document.activeElement).toBe(entries[0]);
    expect(entries[2].className).toContain("text-danger");
  });

  it("moves with the arrow keys, closes with Escape and returns focus to the button", () => {
    render(<MoreMenu items={items()} />);
    const trigger = screen.getByRole("button", { name: "More actions" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const entries = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(entries[0]);
    fireEvent.keyDown(entries[0], { key: "ArrowDown" });
    expect(document.activeElement).toBe(entries[1]);
    fireEvent.keyDown(entries[1], { key: "End" });
    expect(document.activeElement).toBe(entries[2]);
    fireEvent.keyDown(entries[2], { key: "ArrowDown" });
    expect(document.activeElement).toBe(entries[0]);                                // wraps
    fireEvent.keyDown(entries[0], { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("runs the chosen action, closes and returns focus to the button", () => {
    const onEdit = vi.fn();
    render(<MoreMenu items={items(onEdit)} />);
    const trigger = screen.getByRole("button", { name: "More actions" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("shows a single action as a plain button, and nothing when there are none", () => {
    const onCancel = vi.fn();
    const { rerender, container } = render(<MoreMenu items={[{ label: "Cancel transfer", danger: true, onSelect: onCancel }, false]} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel transfer" }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
    rerender(<MoreMenu items={[false, null]} />);
    expect(container.textContent).toBe("");
  });
});

describe("PageHeader with mobileActions", () => {
  it("hides the desktop actions below 1024px and shows the mobile ones only there", () => {
    render(<PageHeader title="SRQ-1" actions={<Button>Desktop edit</Button>} mobileActions={<MoreMenu items={items()} />} />);
    expect(screen.getByRole("button", { name: "Desktop edit" }).parentElement?.className).toContain("max-lg:hidden");
    expect(screen.getByRole("button", { name: "More actions" }).closest("div.lg\\:hidden")).toBeTruthy();
  });

  it("shows a status note once, at every size, before the actions", () => {
    render(<PageHeader title="TRF-1" status={<span>To be collected by Sam</span>} actions={<Button>Cancel</Button>} mobileActions={<MoreMenu items={items()} />} />);
    const note = screen.getAllByText("To be collected by Sam");
    expect(note).toHaveLength(1);
    expect(note[0].parentElement?.className).not.toMatch(/hidden/);
    expect(note[0].nextElementSibling?.textContent).toBe("Cancel");
  });

  it("leaves a header without mobileActions as it was", () => {
    render(<PageHeader title="Products" actions={<Button>Add product</Button>} />);
    expect(screen.getByRole("button", { name: "Add product" }).parentElement?.className).not.toContain("max-lg:hidden");
  });
});

describe("MobileActionBar", () => {
  it("is a named group docked at the bottom below 1024px (safe area included) and inline on wider screens", () => {
    render(<MobileActionBar><Button variant="primary">Submit count</Button></MobileActionBar>);
    const bar = screen.getByRole("group", { name: "Page actions" });
    expect(bar.className).toContain("max-lg:fixed");
    expect(bar.className).toContain("max-lg:bottom-0");
    expect(bar.className).toContain("env(safe-area-inset-bottom)");
    expect(bar.className).not.toContain("lg:hidden");
    expect(screen.getByRole("button", { name: "Submit count" })).toBeTruthy();
  });

  it("can stay out of wide screens when the page header already shows the action", () => {
    render(<MobileActionBar desktop="hidden"><Button variant="primary">Approve…</Button></MobileActionBar>);
    expect(screen.getByRole("group", { name: "Page actions" }).className).toMatch(/(^| )lg:hidden( |$)/);
  });

  it("drops back into the page while a text field is focused on a touch screen (the keyboard is open)", () => {
    const mq = (coarse: boolean) => (q: string) => ({ matches: q.includes("coarse") ? coarse : false, media: q, addEventListener: () => {}, removeEventListener: () => {} });
    vi.stubGlobal("matchMedia", vi.fn(mq(true)));
    render(<><input aria-label="Counted" /><MobileActionBar><Button variant="primary">Submit count</Button></MobileActionBar></>);
    const bar = screen.getByRole("group", { name: "Page actions" });
    expect(bar.className).toContain("max-lg:fixed");
    fireEvent.focusIn(screen.getByLabelText("Counted"));
    expect(bar.className).not.toContain("max-lg:fixed");
    fireEvent.focusOut(screen.getByLabelText("Counted"), { relatedTarget: null });
    expect(bar.className).toContain("max-lg:fixed");
    vi.unstubAllGlobals();
  });
});
