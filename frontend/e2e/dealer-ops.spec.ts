import { expect, test, type Page } from "@playwright/test";
import { apiAs, json, login, PASSWORD, RM, setup, SR, today, WM } from "./helpers";

// Dealer operations: a backorder covered by a transfer (tagged both ways), filling backorders after a receipt,
// scroll cues and selected states on a phone, search the way people type, and the Dealer history tab.

async function backorder(tag: string) {
  // A dealer sells 2 of a tyre the warehouse doesn't have: their replacement is a backorder of 2.
  const f = await setup({ resellerStock: 4, target: 4, warehouseStock: 0, tag });
  const rm = await apiAs(RM);
  const sale = await json<{ lines: { replenishment: { id: number; number: string }[] }[] }>(await rm.post("/api/sales", {
    data: { location_id: f.locationId, sale_date: today(), lines: [{ product_id: f.productId, quantity: 2 }] } }));
  await rm.dispose();
  return { f, request: sale.lines[0].replenishment[0] };
}

test("a backorder is covered by a transfer in two clicks, and the chain shows on both dealers' requests", async ({ page }) => {
  const { f, request } = await backorder("CHN");
  // Another dealer holds the same tyre.
  const giver = await setup({ resellerStock: 0, warehouseStock: 0, tag: "CHG" });
  const wm = await apiAs(WM);
  await json(await wm.post("/api/inventory/opening-balances", { data: { location_id: giver.locationId, lines: [{ product_id: f.productId, quantity: 5 }] } }));

  await login(page, RM);
  await page.goto(`/replenishment/${request.id}`);
  await page.getByRole("link", { name: "Cover with a transfer" }).click();
  await page.waitForURL(/\/transfers\/new\?/);
  // Already filled in and linked to the backorder.
  await expect(page.getByLabel("Fulfils existing backorder?")).toHaveValue(String(request.id));
  await expect(page.getByLabel("Quantity")).toHaveValue("2");
  await expect(page.getByLabel("Reason")).toHaveValue(`Covers backorder ${request.number}`);
  await page.getByRole("button", { name: "Check availability" }).click();
  await page.getByRole("radio", { name: `Select ${giver.locationCode}` }).check();
  await page.getByRole("button", { name: `Use ${giver.locationCode}` }).click();
  await page.getByRole("button", { name: "Approve transfer & reserve stock" }).click();
  await page.waitForURL(/\/transfers\/\d+$/);
  const transferId = Number(page.url().split("/").pop());

  // The giving dealer's replacement is raised on collection and tagged to the backorder it filled.
  await json(await wm.post(`/api/transfers/${transferId}/collect`, { data: {} }));
  await page.goto(`/replenishment/${request.id}`);
  await expect(page.getByText("Transfer link")).toBeVisible();
  await expect(page.getByText("Covered by")).toBeVisible();
  const replacement = page.getByText(/’s replacement/).locator("a");
  await expect(replacement).toBeVisible();
  await replacement.click();
  await expect(page.getByText(/Replacement for .*which filled/)).toContainText(request.number);
  await wm.dispose();
});

test("after Receive goods, the backorders the tyres can fill are offered and filled in one click", async ({ page }) => {
  const { f, request } = await backorder("RCV");
  await login(page, WM);
  await page.goto("/purchasing");
  await page.getByRole("button", { name: "Receive without PO" }).click();
  const dialog = page.getByRole("dialog", { name: "Receive goods (no purchase order)" });
  await dialog.getByRole("combobox").first().fill(f.sku);
  await dialog.getByRole("option", { name: new RegExp(f.sku) }).first().click();
  await dialog.getByLabel("Received").fill("3");
  await dialog.getByRole("button", { name: "Post receipt" }).click();
  const offer = page.getByText(/backorder\(s\) can be filled now/).locator("xpath=ancestor::*[contains(@class,'rounded-card')][1]");
  await expect(offer).toContainText(request.number);
  await offer.getByRole("button", { name: /^Fill \d+ backorder/ }).click();
  await expect(page.getByText(/Reserved stock for \d+ backorder\(s\)/)).toBeVisible();
  const rm = await apiAs(RM);
  const req = await json<{ qty_allocated: number; qty_awaiting_supply: number }>(await rm.get(`/api/replenishment/requests/${request.id}`));
  expect([req.qty_allocated, req.qty_awaiting_supply]).toEqual([2, 0]);
  await rm.dispose();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("tabs that don't fit show an arrow to the right; the selected tab is clearly marked", async ({ page }) => {
    const f = await setup({ resellerStock: 2, warehouseStock: 0, tag: "TAB" });
    // Phones: the sidebar is behind the menu button, so sign in without waiting for it.
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(RM);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL((u) => u.pathname === "/");
    await page.goto(`/resellers/${f.resellerId}`);
    const tablist = page.getByRole("tablist");
    await expect(page.getByRole("tab", { name: "Dealer history" })).toHaveCount(1);
    expect(await tablist.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    const rightCue = tablist.locator("xpath=following-sibling::div[contains(@class,'bg-linear-to-l')]");
    await expect(rightCue).toHaveCount(1);
    await expect(rightCue.locator("svg")).toBeVisible();                        // the arrow
    const selected = page.getByRole("tab", { selected: true });
    expect(await selected.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(255, 248, 214)");   // pale yellow
    expect(Number(await selected.evaluate((el) => getComputedStyle(el).fontWeight))).toBeGreaterThanOrEqual(600);
    await tablist.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
    await expect(rightCue).toHaveCount(0);                                      // gone at the end
    // Choosing a tab off the right edge scrolls it into view and marks it.
    await page.getByRole("tab", { name: "Profile" }).click();
    await expect(page.getByRole("tab", { name: "Profile" })).toHaveAttribute("aria-selected", "true");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});

async function pickProduct(page: Page, label: string, query: string) {
  const box = page.getByLabel(label);
  await box.fill(query);
  return page.getByRole("listbox", { name: "Products" }).getByRole("option");
}

test("search the way people type: '205 55' and part of the pattern find the tyre; Check Stock shows it as you type", async ({ page }) => {
  const f = await setup({ resellerStock: 0, warehouseStock: 7, tag: "SRCH" });
  const pattern = f.sku.replace(/^E2E-/, "").toLowerCase();     // the setup tyre is "E2E Pattern <run> 205/55R16 91V"
  await login(page, RM);
  await page.goto("/stock-check");
  await page.getByLabel("Tyre", { exact: true }).fill(`${pattern} 205 55`);       // no slash, no Search button
  await expect(page.getByText("Main warehouse · available")).toBeVisible();
  await expect(page.getByText("Main warehouse · available").locator("xpath=..")).toContainText("7");
  // The tyre picker in forms: "205 55 r16" with the run code.
  await page.goto("/transfers/new");
  const options = await pickProduct(page, "Exact SKU required", `${pattern} 20555 r16`);
  await expect(options).toHaveCount(1);
  await expect(options.first()).toContainText(f.sku);
  // A table search box: Warehouse stock.
  await page.goto("/warehouse");
  await page.getByRole("searchbox", { name: "Search table" }).fill(`${pattern} 205-55`);
  await expect(page.getByRole("table", { name: "Warehouse stock" }).locator("tbody tr")).toHaveCount(1);
});

test("Dealer history: joined when and with what stock, existing dealer, first consignment and sales so far", async ({ page }) => {
  const { f } = await backorder("HST");   // opening stock of 4, then a sale of 2
  await login(page, RM);
  await page.goto(`/resellers/${f.resellerId}`);
  await page.getByRole("tab", { name: "Dealer history" }).click();
  await expect(page.getByText("Existing dealer (joined with stock)")).toBeVisible();
  await expect(page.getByText("Onboarded with this stock")).toBeVisible();
  await expect(page.getByRole("table", { name: "Onboarding stock" })).toContainText(f.sku);
  await expect(page.getByText("2 in 1 sale")).toBeVisible();
  await expect(page.getByText(/Initial stock loaded/).first()).toBeVisible();
  // Sales Reps don't get the tab.
  await login(page, SR);
  await page.goto(`/resellers/${f.resellerId}`);
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Dealer history" })).toHaveCount(0);
});
