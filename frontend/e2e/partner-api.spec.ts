import { expect, request, test } from "@playwright/test";
import { ADMIN, BASE, json, login, setup, WM } from "./helpers";

// Website stock API (Stage A): an Administrator creates a key, the website's server reads In stock / Low / Out with it,
// and revoking the key stops it working.

test("Administrator creates a website key, the API answers with status bands only, and revoking it stops access", async ({ page }) => {
  const low = await setup({ resellerStock: 0, warehouseStock: 3, tag: "PAL" });
  const plenty = await setup({ resellerStock: 9, warehouseStock: 12, tag: "PAI" });

  await login(page, ADMIN);
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Website access" }).click();
  await page.getByRole("button", { name: "New key" }).click();
  const dialog = page.getByRole("dialog", { name: "New website access key" });
  await dialog.getByLabel("Name").fill("E2E website");
  await dialog.getByRole("button", { name: "Create key" }).click();
  const shown = page.getByRole("dialog", { name: "Copy this key now" });
  const key = await shown.getByLabel("Website access key").inputValue();
  expect(key).toMatch(/^tg_live_/);
  await shown.getByRole("button", { name: "Done" }).click();
  const row = page.getByRole("row", { name: /E2E website/ });
  await expect(row).toContainText("Active");
  await expect(row).toContainText(key.slice(0, 12));
  await expect(page.getByText(key)).toHaveCount(0);                     // never shown again

  // The website's server: no login, just the key.
  const site = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { "X-API-Key": key } });
  const all = await json<{ items: { sku: string; status: string }[] }>(await site.get("/api/partner/v1/stock"));
  const status = Object.fromEntries(all.items.map((i) => [i.sku, i.status]));
  expect(status[low.sku]).toBe("LOW");
  expect(status[plenty.sku]).toBe("IN_STOCK");
  const one = await site.get(`/api/partner/v1/stock/${plenty.sku}`);
  expect(Object.keys(await one.json()).sort()).toEqual(["name", "size", "sku", "status"]);
  expect(one.headers()["cache-control"]).toBe("private, max-age=60");
  // A staff login is not enough, and other roles cannot manage keys.
  const wm = await request.newContext({ baseURL: BASE });
  expect((await wm.get("/api/partner/v1/stock")).status()).toBe(401);
  await wm.post("/api/auth/login", { data: { email: WM, password: process.env.E2E_PASSWORD ?? "e2e-password-123" } });
  expect((await wm.get("/api/partner-keys")).status()).toBe(403);

  await page.reload();
  await page.getByRole("tab", { name: "Website access" }).click();
  await expect(page.getByRole("row", { name: /E2E website/ })).not.toContainText("Never");   // last used is recorded
  await page.getByRole("button", { name: "Revoke E2E website" }).click();
  await page.getByRole("dialog", { name: "Revoke E2E website" }).getByRole("button", { name: "Revoke key" }).click();
  await expect(page.getByRole("row", { name: /E2E website/ })).toContainText("Revoked");
  expect((await site.get("/api/partner/v1/stock")).status()).toBe(401);
  await site.dispose();
  await wm.dispose();
});
