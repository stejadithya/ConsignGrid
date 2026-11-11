/**
 * UAT round 2: sign-in rules, dealer onboarding, receipts, the stock transfer journey and stock check scheduling.
 * Run only against a disposable database (see helpers.ts). Each scenario creates its own data.
 */
import { expect, test } from "@playwright/test";
import { apiAs, dealerDetails, json, login, RM, selectByPrefix, setup, SR, today, WM } from "./helpers";

const stamp = () => Date.now().toString(36);

test("J1 five wrong passwords lock the account; the RM unlocks it; a too-long new password is refused", async ({ page }) => {
  // A throwaway user, so the shared test accounts are never locked.
  const rm = await apiAs(RM);
  const email = `lock-${stamp()}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: `Guard Rep ${stamp()}`, password: "temporary-pass-1", role: "SALES_REP" } }));
  await page.goto("about:blank");
  await page.context().clearCookies();
  await page.goto("/login");
  for (let i = 0; i < 5; i++) {
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(`wrong-password-${i}`);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText(i < 4 ? "Invalid email or password" : /Too many wrong passwords/)).toBeVisible();
  }
  // Even the right password is refused while locked.
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(/Too many wrong passwords/)).toBeVisible();

  // The Relationship Manager sees "Locked" and unlocks it.
  await login(page, RM);
  await page.goto("/admin");
  const row = page.getByRole("table", { name: "Users" }).getByRole("row").filter({ hasText: email });
  await expect(row).toContainText("Locked");
  await row.click();
  await page.getByRole("button", { name: "Unlock now" }).click();
  await expect(row).not.toContainText("Locked");

  // They can sign in again; the forced new password can't be longer than 72 bytes.
  await page.goto("about:blank");
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill("é".repeat(40));
  await expect(page.getByText(/Too long: use 72 characters or fewer/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Save new password" })).toBeDisabled();
  await rm.dispose();
});

test("J2/J3 new dealer: reference is automatic and locked; first stock is ordered, not loaded; shops read dealer first", async ({ page }) => {
  await login(page, RM);
  await page.goto("/resellers");
  await page.getByRole("button", { name: /New dealer/ }).first().click();
  const form = page.getByRole("dialog", { name: "New dealer" });
  await expect(form.getByRole("textbox", { name: /Account reference/ })).toBeDisabled();
  await form.getByRole("button", { name: "Cancel" }).click();

  // A new dealer (added through the API) is offered "Order stock", not "Initial stock"; initial stock is refused.
  const rm = await apiAs(RM);
  const run = `NEW${stamp().toUpperCase()}`;
  const dealer = await json<{ id: number; locations: { id: number; code: string }[] }>(await rm.post("/api/resellers", { data: {
    ...(await dealerDetails(rm, run)), business_name: `Roskill ${run}`, joined_with_stock: false,
    locations: [{ name: "Main shop", address_line1: "1 Test Street", city: "Auckland" }] } }));
  await page.goto(`/resellers/${dealer.id}`);
  await expect(page.getByRole("link", { name: "Order stock" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Initial stock" })).toHaveCount(0);
  const f = await setup({ resellerStock: 0, warehouseStock: 5, tag: "J3" });
  const refused = await rm.post(`/api/resellers/${dealer.id}/initial-stock`, { data: {
    location_id: dealer.locations[0].id, lines: [{ product_id: f.productId, quantity: 2 }] } });
  expect(refused.status()).toBe(422);

  // "Order stock" opens a stock request for that shop; the shop is named dealer first.
  await page.getByRole("link", { name: "Order stock" }).first().click();
  await page.waitForURL(/\/stock-requests\/new\?location=/);
  const shop = page.getByLabel("Dealer location");
  await expect(shop.locator("option:checked")).toHaveText(`Roskill ${run} — Main shop (Auckland) · ${dealer.locations[0].code}`);
  await rm.dispose();
});

test("J4 goods received without a PO show the tyre name and size, not just the SKU", async ({ page }) => {
  const f = await setup({ resellerStock: 0, warehouseStock: 0, tag: "J4" });
  await login(page, WM);
  await page.goto("/purchasing");
  await page.getByRole("button", { name: "Receive without PO" }).click();
  const dialog = page.getByRole("dialog", { name: "Receive goods (no purchase order)" });
  await dialog.getByRole("combobox").first().fill(f.sku);
  await dialog.getByRole("option", { name: new RegExp(f.sku) }).first().click();
  await dialog.getByLabel("Received").fill("2");
  await dialog.getByRole("button", { name: "Post receipt" }).click();
  await page.getByRole("tab", { name: "Goods receipts" }).click();
  const row = page.getByRole("table", { name: "Receipts" }).getByRole("row").filter({ hasText: f.sku }).first();
  await expect(row).toContainText("205/55R16");
  await expect(row).toContainText(f.sku);
});

test("J5 order 7 with 4 in the warehouse: approve 4, arrange 3 from another dealer via the warehouse, with evidence", async ({ page }) => {
  const b = await setup({ resellerStock: 0, warehouseStock: 4, tag: "J5B" });
  const a = await setup({ resellerStock: 0, warehouseStock: 0, tag: "J5A" });
  const wm = await apiAs(WM);
  await json(await wm.post("/api/inventory/opening-balances", { data: { location_id: a.locationId, lines: [{ product_id: b.productId, quantity: 5 }] } }));
  const rep = await apiAs(SR);
  const me = await json<{ id: number; full_name: string }>(await rep.get("/api/auth/me"));
  const sr = await json<{ id: number; number: string }>(await rep.post("/api/stock-requests", { data: {
    location_id: b.locationId, submit: true, lines: [{ product_id: b.productId, quantity: 7 }] } }));

  // The Warehouse Manager approves 4 and arranges the other 3 from another dealer, in one go.
  await login(page, WM);
  await page.goto(`/stock-requests/${sr.id}`);
  await page.getByRole("button", { name: "Approve…" }).click();
  const decide = page.getByRole("dialog");
  await decide.getByLabel(`Remainder for ${b.sku}`).selectOption("TRANSFER");
  await decide.getByRole("button", { name: "Partially approve" }).click();
  const details = page.getByRole("dialog", { name: "Approval details" });
  await expect(details).toContainText("3 to arrange from another dealer");
  await details.getByLabel("How was it approved").selectOption("IN_PERSON");
  await details.getByLabel("Spoke to").fill("Rep in the warehouse");
  await details.getByLabel("Comments").fill("4 now, 3 from another dealer");
  await details.getByRole("button", { name: "Confirm approval" }).click();
  const arranged = page.getByText(/Arranged from another dealer: 3/);
  await expect(arranged).toBeVisible();
  await arranged.getByRole("link").click();
  await page.waitForURL(/\/transfers\/\d+$/);
  const transferId = Number(page.url().split("/").pop());

  // Choose the dealer who holds it; the rep collects and brings it to the warehouse.
  await page.getByRole("button", { name: "Approve & choose source" }).first().click();
  const approve = page.getByRole("dialog", { name: "Approve transfer" });
  await selectByPrefix(approve.getByLabel("Source location"), a.locationCode);
  await approve.getByLabel("Arrange the pick-up now").check();
  await approve.getByText("Sales representative", { exact: true }).click();
  await approve.getByRole("combobox", { name: /Sales representative/ }).selectOption({ label: me.full_name });
  await approve.getByText("Via the warehouse", { exact: true }).click();
  await approve.getByRole("button", { name: "Approve & reserve" }).click();
  await expect(page.getByText("Via the warehouse (received and checked there)")).toBeVisible();
  await json(await rep.post(`/api/transfers/${transferId}/collect`, { data: { collected_from_name: "Sam at the other dealer" } }));
  const early = await rep.post(`/api/transfers/${transferId}/receive`, { data: { received_by_name: "Owner", notes: "Too early" } });
  expect(early.status()).toBe(409);

  // The warehouse records it received and checked them.
  await page.reload();
  await page.getByRole("button", { name: "Received at the warehouse" }).first().click();
  const check = page.getByRole("dialog", { name: "Received at the warehouse" });
  await check.getByLabel(/What arrived and its condition/).fill("3 arrived, good condition");
  await check.getByRole("button", { name: "Received and checked" }).click();
  await expect(page.getByText(/3 arrived, good condition/).first()).toBeVisible();

  // The rep delivers with the hand-over details; the backorder is filled.
  const done = await json<{ status: string }>(await rep.post(`/api/transfers/${transferId}/receive`, { data: {
    received_by_name: "Shop owner", notes: "Handed over at the counter" } }));
  expect(done.status).toBe("COMPLETED");
  const line = (await json<{ lines: { qty_delivered: number; qty_backorder_open: number }[] }>(await wm.get(`/api/stock-requests/${sr.id}`))).lines[0];
  expect([line.qty_delivered, line.qty_backorder_open]).toEqual([3, 0]);
  await wm.dispose();
  await rep.dispose();
});

test("J9 a stock check can be moved up to 14 days ahead with a reason", async ({ page }) => {
  const f = await setup({ resellerStock: 1, warehouseStock: 0, tag: "J9" });
  await login(page, WM);
  await page.goto(`/resellers/${f.resellerId}`);
  await page.getByRole("tab", { name: "Stocktakes" }).click();
  const card = page.getByRole("table", { name: "Next stock check" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: /^Move/ }).click();
  const move = page.getByRole("dialog", { name: /Move stock check/ });
  const in5 = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
  await move.getByLabel("New date").fill(in5);
  await move.getByLabel(/Why can't it happen on time/).fill("Owner away until next week");
  await move.getByRole("button", { name: "Move stock check" }).click();
  await expect(move).toBeHidden();
  await expect(card).toContainText("Owner away until next week");
  await expect(card).toContainText("Due soon");
  // More than 14 days ahead is refused by the server too.
  const wm = await apiAs(WM);
  const far = await wm.post(`/api/stocktakes/schedule/${f.locationId}/reschedule`, { data: {
    date: new Date(Date.now() + 20 * 864e5).toISOString().slice(0, 10), reason: "Too far" } });
  expect(far.status()).toBe(422);
  expect(today()).toBeTruthy();
  await wm.dispose();
});
