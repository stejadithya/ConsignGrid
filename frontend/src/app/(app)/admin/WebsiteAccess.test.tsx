import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminPage from "./page";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { id: 1, full_name: "Root", role: "ADMINISTRATOR", reseller_id: null }, can: () => true }),
}));

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const keys = [{ id: 1, name: "Old website", key_prefix: "tg_live_ab12", created_at: "2026-10-20T09:00:00Z", created_by: "Root",
  last_used_at: null, revoked_at: null }];
let posted: string[] = [];

beforeEach(() => {
  posted = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, "http://localhost");
    if (url.pathname === "/api/partner-keys" && init?.method === "POST") {
      posted.push(String(init.body));
      return reply({ ...keys[0], id: 2, name: "Customer website", key_prefix: "tg_live_zz99", key: "tg_live_zz99-secret-value" }, 201);
    }
    if (url.pathname === "/api/partner-keys") return reply(keys);
    return reply([]);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Admin → Website access", () => {
  it("lists keys by prefix only and shows a new key once", async () => {
    render(<AdminPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Website access" }));
    await waitFor(() => expect(screen.getByText("Old website")).toBeTruthy());
    expect(screen.getByText("tg_live_ab12…")).toBeTruthy();
    expect(screen.getByText("Never")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "New key" }));
    const dialog = screen.getByRole("dialog", { name: "New website access key" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create key" }));
    const shown = await screen.findByRole("dialog", { name: "Copy this key now" });
    expect(within(shown).getByLabelText<HTMLInputElement>("Website access key").value).toBe("tg_live_zz99-secret-value");
    expect(JSON.parse(posted[0])).toEqual({ name: "Customer website" });
    fireEvent.click(within(shown).getByRole("button", { name: "Done" }));
    expect(screen.queryByDisplayValue("tg_live_zz99-secret-value")).toBeNull();
  });

  it("asks for confirmation before revoking, with an explicit destructive label", async () => {
    render(<AdminPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Website access" }));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke Old website" }));
    const confirm = screen.getByRole("dialog", { name: "Revoke Old website" });
    expect(within(confirm).getByRole("button", { name: "Revoke key" }).className).toContain("bg-danger");
  });
});
