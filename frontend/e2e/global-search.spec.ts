/**
 * One search box across the app (option B). Run only against a disposable database (see helpers.ts).
 */
import { expect, test } from "@playwright/test";
import { apiAs, json, login, PASSWORD, RM, setup } from "./helpers";

async function dealerLogin(resellerId: number) {
  const rm = await apiAs(RM);
  const r = await json<{ email: string }>(await rm.get(`/api/resellers/${resellerId}`));
  const email = `search-${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: `Dealer ${r.email}`, password: "temporary-pass-1", role: "RESELLER", reseller_id: resellerId } }));
  await rm.dispose();
  return email;
}

test("staff find a stock request by its number from the top bar and Enter opens it", async ({ page }) => {
  const f = await setup({ resellerStock: 0, warehouseStock: 5, tag: "GSA" });
  const rm = await apiAs(RM);
  const sr = await json<{ id: number; number: string }>(await rm.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 2 }] } }));
  await rm.dispose();
  await login(page, RM);
  const box = page.getByRole("combobox", { name: "Search everything" });
  await box.fill(sr.number.toLowerCase().replace("-", " "));          // "srq 000123"
  const results = page.getByRole("listbox", { name: "Search results" });
  await expect(results.getByRole("option", { name: new RegExp(sr.number) })).toBeVisible();
  await box.press("Enter");
  await page.waitForURL(`**/stock-requests/${sr.id}`);

  // Dealers and tyres too: the dealer by name, the tyre by size and SKU.
  await box.fill(`E2E Reseller ${f.sku.replace("E2E-", "")}`);
  await results.getByRole("group", { name: "Dealers" }).getByRole("option").first().click();
  await page.waitForURL(`**/resellers/${f.resellerId}`);
  await box.fill(f.sku);
  await expect(results.getByRole("group", { name: "Tyres" })).toContainText("205/55R16");
});

test("a dealer finds only their own documents", async ({ page }) => {
  const a = await setup({ resellerStock: 0, warehouseStock: 5, tag: "GSB" });
  const b = await setup({ resellerStock: 0, warehouseStock: 5, tag: "GSC" });
  const rm = await apiAs(RM);
  const theirs = await json<{ number: string }>(await rm.post("/api/stock-requests", { data: {
    location_id: b.locationId, submit: true, lines: [{ product_id: b.productId, quantity: 1 }] } }));
  const mine = await json<{ number: string }>(await rm.post("/api/stock-requests", { data: {
    location_id: a.locationId, submit: true, lines: [{ product_id: a.productId, quantity: 1 }] } }));
  await rm.dispose();
  const email = await dealerLogin(a.resellerId);
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill(`${PASSWORD}-dealer`);
  await page.getByLabel("Confirm new password").fill(`${PASSWORD}-dealer`);
  await page.getByRole("button", { name: "Save new password" }).click();
  const box = page.getByRole("combobox", { name: "Search everything" });
  await box.fill(theirs.number);
  await expect(page.getByText(/Nothing found for/)).toBeVisible();
  await box.fill(mine.number);
  await expect(page.getByRole("listbox", { name: "Search results" })).toContainText(mine.number);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("the search icon opens a full-width search; nothing scrolls sideways", async ({ page }) => {
    const f = await setup({ resellerStock: 1, warehouseStock: 0, tag: "GSP" });
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(RM);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL((u) => u.pathname === "/");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    const box = page.getByRole("combobox", { name: "Search everything" });
    await expect(box).toBeFocused();
    await box.fill(`E2E Reseller ${f.sku.replace("E2E-", "")}`);
    await page.getByRole("listbox", { name: "Search results" }).getByRole("option").first().click();
    await page.waitForURL(`**/resellers/${f.resellerId}`);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
