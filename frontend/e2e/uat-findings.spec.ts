/**
 * Release 1.11 UAT findings, end to end. Run only against a disposable database (see helpers.ts).
 * Each scenario creates its own data through the API.
 */
import { expect, test, type Page } from "@playwright/test";
import { apiAs, balance, json, login, pickProduct, RM, selectByPrefix, setup, SR, today, WM } from "./helpers";
import { xlsx } from "./xlsx";

const stamp = () => Date.now().toString(36);

/** A new staff login made by the Relationship Manager; the first sign-in forces a personal password. */
async function newStaffUser(page: Page, role: string, name: string) {
  const rm = await apiAs(RM);
  const email = `${role.toLowerCase()}-${stamp()}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: name, password: "temporary-pass-1", role } }));
  await rm.dispose();
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill("first-own-pass-2");
  await page.getByLabel("Confirm new password").fill("first-own-pass-2");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  return { email, password: "first-own-pass-2" };
}

test("(1) Change password opens a roomy dialog and the new password works", async ({ page }) => {
  const who = await newStaffUser(page, "SALES_REP", "Pat Password");
  await page.getByRole("button", { name: /Account menu for Pat Password/ }).click();
  await page.getByRole("menuitem", { name: "Change password" }).click();
  const dialog = page.getByRole("dialog", { name: "Change your password" });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThan(300);
  await expect(dialog.getByText("at least 10 characters")).toBeVisible();
  await dialog.getByLabel("Current password").fill(who.password);
  await dialog.getByLabel("New password", { exact: true }).fill("changed-pass-3");
  await dialog.getByRole("button", { name: "Show password" }).nth(1).click();
  await expect(dialog.getByLabel("New password", { exact: true })).toHaveAttribute("type", "text");
  await dialog.getByLabel("Confirm new password").fill("changed-pass-3");
  await dialog.getByRole("button", { name: "Save new password" }).click();
  await expect(dialog.getByText("Password changed")).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).last().click();
  await expect(dialog).toBeHidden();
  // Sign out, then sign in with the new password.
  await page.getByRole("button", { name: /Account menu for Pat Password/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL(/\/login/);
  await login(page, who.email, "changed-pass-3");
});

/** A dealer login for a fixture dealer (forced password change skipped: the API sets it, the test never signs in). */
async function dealerApi(resellerId: number) {
  const rm = await apiAs(RM);
  const email = `dealer-${stamp()}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: "E2E Dealer", password: "temporary-pass-1", role: "RESELLER", reseller_id: resellerId } }));
  await rm.dispose();
  return apiAs(email, "temporary-pass-1");
}

test("(2) a new stock request pops up a toast for the Warehouse Manager, and Open goes to it", async ({ page }) => {
  const f = await setup({ resellerStock: 0, warehouseStock: 10, tag: "NTF" });
  await login(page, WM);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);   // the first poll has run and set the baseline
  // Dismiss any summary toast from earlier notifications.
  for (const d of await page.getByRole("button", { name: "Dismiss notification" }).all()) await d.click();
  const dealer = await dealerApi(f.resellerId);
  const sr = await json<{ id: number; number: string }>(await dealer.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 2 }] } }));
  const toasts = page.getByRole("status", { name: "New notifications" });
  const toast = toasts.locator("> div", { hasText: `${sr.number} is waiting for approval` });
  await expect(toast).toBeVisible({ timeout: 25_000 });
  await expect(page).toHaveTitle(/^\(\d+\+?\) /);
  await toast.getByRole("button", { name: "Open" }).click();
  await page.waitForURL(new RegExp(`/stock-requests/${sr.id}$`));
  await expect(page.getByText(sr.number).first()).toBeVisible();
});

const MONEY = /(\$\s?\d)|\bNZD\b|\bAUD\b|\bRRP\b|\bMRP\b|dealer price|unit price|net value|subtotal|value at cost/i;

/** Sign in with a temporary password and choose a personal one. */
async function firstSignIn(page: Page, email: string) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill("own-pass-12345");
  await page.getByLabel("Confirm new password").fill("own-pass-12345");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

async function expectNoMoney(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  const text = await page.locator("body").innerText();
  const hit = text.match(MONEY);
  expect(hit, `${url} shows "${hit?.[0]}"`).toBeNull();
}

test("(3) no prices anywhere, for every role", async ({ page }) => {
  test.setTimeout(240_000);
  const f = await setup({ resellerStock: 6, target: 6, warehouseStock: 10, tag: "NOP" });
  const rm = await apiAs(RM);
  const dealerEmail = `nop-dealer-${stamp()}@e2e.example.com`;
  const fmEmail = `nop-fm-${stamp()}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email: dealerEmail, full_name: "Nora Dealer", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));
  await json(await rm.post("/api/users", { data: { email: fmEmail, full_name: "Fin Manager", password: "temporary-pass-1", role: "FINANCE_MANAGER" } }));
  // Data behind the detail pages: a sale (with its replacement), an invoice record and a stock request.
  const sale = await json<{ id: number; lines: { id: number; replenishment: { id: number }[] }[] }>(await rm.post("/api/sales", { data: {
    location_id: f.locationId, sale_date: today(), lines: [{ product_id: f.productId, quantity: 1 }] } }));
  const inv = await json<{ id: number }>(await rm.post("/api/invoices", { data: { reseller_id: f.resellerId, sale_line_ids: [sale.lines[0].id] } }));
  const sr = await json<{ id: number }>(await rm.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 1 }] } }));
  await rm.dispose();
  const details = [`/resellers/${f.resellerId}`, `/products/${f.productId}`, `/sales?sale=${sale.id}`, `/invoices/${inv.id}`,
    `/stock-requests/${sr.id}`, ...(sale.lines[0].replenishment[0] ? [`/replenishment/${sale.lines[0].replenishment[0].id}`] : [])];

  const sweep = async () => {
    const hrefs = await page.getByRole("navigation", { name: "Main" }).locator("a[href]").evaluateAll(
      (as) => [...new Set(as.map((a) => a.getAttribute("href") ?? "").filter((h) => h.startsWith("/")))]);
    for (const href of [...hrefs, ...details]) await expectNoMoney(page, href);
  };
  for (const who of [RM, WM, SR]) { await login(page, who); await sweep(); }
  await firstSignIn(page, fmEmail); await sweep();
  await firstSignIn(page, dealerEmail); await sweep();
});

test("(4) Check Stock searches only once there is something to find; a request page checks only its own tyres", async ({ page }) => {
  const a = await setup({ resellerStock: 3, warehouseStock: 12, tag: "CKA" });
  const b = await setup({ resellerStock: 0, warehouseStock: 5, tag: "CKB" });
  await login(page, WM);
  let calls = 0;
  page.on("request", (r) => { if (/\/api\/(products\?|transfers\/sources)/.test(r.url())) calls += 1; });
  await page.goto("/stock-check");
  const box = page.getByLabel("Tyre", { exact: true });
  await expect(box).toHaveValue("");
  // Nothing is searched on opening or for one or two characters.
  await box.fill(a.sku.slice(0, 2));
  await page.waitForTimeout(800);
  expect(calls).toBe(0);
  await expect(page.getByText("Main warehouse · available")).toHaveCount(0);
  // From three characters it searches as you type; the Search button still works.
  await box.fill(a.sku);
  await expect(page.getByText("Main warehouse · available")).toBeVisible();
  expect(calls).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("Main warehouse · available")).toBeVisible();

  // A stock request for tyre A shows availability for A only (B is never mentioned).
  const rm = await apiAs(RM);
  const sr = await json<{ id: number }>(await rm.post("/api/stock-requests", { data: {
    location_id: a.locationId, submit: true, lines: [{ product_id: a.productId, quantity: 2 }] } }));
  await rm.dispose();
  await page.goto(`/stock-requests/${sr.id}`);
  const rows = page.getByTestId("availability-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText(a.sku);
  await expect(rows.first()).toContainText("Warehouse: Yes – 12 available");
  await expect(rows.first()).toContainText("Already at this dealer: 3");
  await expect(page.getByTestId("availability-row").filter({ hasText: b.sku })).toHaveCount(0);
});

test("(5) an existing dealer with two shops, Excel stock and a login; the dealer signs in and sees their stock", async ({ page }) => {
  const f = await setup({ resellerStock: 0, warehouseStock: 0, tag: "ONB" });
  const run = `R${stamp().toUpperCase()}`;   // a third word starting with R → dealer code OTR
  await login(page, RM);
  await page.goto("/resellers?new=1");
  const form = page.getByRole("dialog");
  await form.getByText("Existing TyreGrow dealer").click();
  await form.getByLabel(/^Business name/).fill(`Onboard Tyres ${run}`);
  await form.getByLabel("Contact name").fill("Olive Onboard");
  await form.getByLabel(/^Email/).fill(`onboard-${run.toLowerCase()}@e2e.example.com`);
  await form.getByLabel(/^Phone/).fill("09 555 0111");
  await form.getByLabel("Sales representative").selectOption({ index: 1 });
  await form.getByLabel("Billing address").fill("1 Onboard Road, Auckland");
  await form.getByLabel("Shop 1 delivery address").fill("1 Onboard Road");
  await form.getByLabel("Shop 1 city").fill("Auckland");
  await form.getByRole("button", { name: "Add another shop" }).click();
  await form.getByLabel("Shop 2 name").fill("Onboard South");
  await form.getByLabel("Shop 2 delivery address").fill("9 South Road");
  await form.getByLabel("Shop 2 city").fill("Manukau");
  // The account reference is generated from the name and the first shop's city; shop codes follow it.
  const refBox = form.getByRole("textbox", { name: /^Account reference/ });
  await expect(refBox).toHaveValue(/^OTR-AUC-\d{3,}$/);   // Onboard · Tyres · R…
  const ref = await refBox.inputValue();
  await form.getByRole("tab", { name: "Upload Excel" }).click();
  await form.getByLabel("Initial stock Excel file").setInputFiles({
    name: "stock.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: xlsx([["SKU Code", "Quantity", "Shop code"], [f.sku, 4, `${ref}-01`], [f.sku, 2, `${ref}-02`]]) });
  await expect(form.getByLabel("Create a login for this dealer")).toBeChecked();
  await form.getByRole("button", { name: "Create dealer and add stock" }).click();
  const password = (await page.getByTestId("temporary-password").textContent()) ?? "";
  expect(password).toMatch(/^[A-Za-z2-9]{12}$/);
  await page.getByRole("button", { name: "Done — open the dealer" }).click();
  await expect(page.getByText(`${ref}`).first()).toBeVisible();

  // The dealer signs in with the temporary password, chooses their own, and sees their stock in both shops.
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(`onboard-${run.toLowerCase()}@e2e.example.com`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill(password);
  await page.getByLabel("New password", { exact: true }).fill("onboard-own-123");
  await page.getByLabel("Confirm new password").fill("onboard-own-123");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByText("My shop", { exact: true })).toBeVisible();
  await page.goto("/consignment");
  await expect(page.getByText(`${ref}-01`).first()).toBeVisible();
  await expect(page.getByText(`${ref}-02`).first()).toBeVisible();
  const rm = await apiAs(RM);
  const dealers = await json<{ id: number; account_ref: string }[]>(await rm.get("/api/resellers"));
  const d = await json<{ locations: { id: number; code: string }[] }>(await rm.get(`/api/resellers/${dealers.find((x) => x.account_ref === ref)!.id}`));
  expect(d.locations.map((l) => l.code)).toEqual([`${ref}-01`, `${ref}-02`]);
});

test("(6) export all SKUs and import the file again: nothing changes", async ({ page }) => {
  await setup({ resellerStock: 0, warehouseStock: 0, tag: "EXP" });   // at least one product exists
  await login(page, WM);
  await page.goto("/products");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export all SKUs (Excel)" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^TyreGrow_SKUs_\d{4}-\d{2}-\d{2}\.xlsx$/);
  const path = await file.path();
  await page.getByRole("button", { name: "Import from Excel" }).click();
  const dialog = page.getByRole("dialog", { name: "Import products from Excel" });
  await dialog.getByLabel("Excel file").setInputFiles(path);
  await dialog.getByRole("button", { name: "Check file" }).click();
  await expect(dialog.getByText(/Checked \d+ row\(s\)/)).toBeVisible();
  const summary = dialog.getByText(/Checked \d+ row\(s\)/).locator("..");
  const total = Number(((await dialog.getByText(/Checked \d+ row\(s\)/).textContent()) ?? "").match(/\d+/)![0]);
  expect(total).toBeGreaterThan(0);
  await expect(summary).toContainText("0 new");
  await expect(summary).toContainText("0 to update");
  await expect(summary).toContainText(`${total} unchanged`);
  await expect(summary).toContainText("0 with errors");
});

test("(7) stock request: pick sheet, WM sends to RM, RM approves with details, rep delivers; a partial gets the kind message", async ({ page }) => {
  const f = await setup({ resellerStock: 1, warehouseStock: 10, tag: "SRQ" });
  const dealer = await dealerApi(f.resellerId);
  const sr = await json<{ id: number; number: string }>(await dealer.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 4 }] } }));

  // The warehouse prints a pick sheet while the request is under review, then sends it to the Relationship Manager.
  await login(page, WM);
  await page.goto(`/stock-requests/${sr.id}`);
  await page.getByRole("link", { name: "Print pick sheet" }).click();
  await expect(page.getByRole("heading", { name: "Pick sheet" })).toBeVisible();
  await expect(page.getByText(f.sku)).toBeVisible();
  await expect(page.getByText(/\$\s?\d/)).toHaveCount(0);
  await page.goto(`/stock-requests/${sr.id}`);
  await page.getByRole("button", { name: "Send to Relationship Manager" }).click();
  const send = page.getByRole("dialog", { name: "Send to Relationship Manager" });
  await send.getByLabel("Relationship Manager").selectOption({ index: 1 });
  await send.getByLabel("Note for the approver").fill("New dealer, big order");
  await send.getByRole("button", { name: "Send for approval" }).click();
  await expect(page.getByText(/Waiting for .+ to approve \(sent by .+: New dealer, big order\)/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve…" })).toHaveCount(0);

  // The Relationship Manager approves with the approval details.
  await login(page, RM);
  await page.goto(`/stock-requests/${sr.id}`);
  await expect(page.getByText("Already at this dealer: 1")).toBeVisible();
  await page.getByRole("button", { name: "Approve…" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve and reserve" }).click();
  const details = page.getByRole("dialog", { name: "Approval details" });
  await details.getByLabel("How was it approved").selectOption("IN_PERSON");
  await details.getByLabel("Spoke to").fill("Owner at the counter");
  await details.getByLabel("Comments").fill("Approved for the opening week");
  await details.getByRole("button", { name: "Confirm approval" }).click();
  await expect(page.getByText("Approved for the opening week")).toBeVisible();

  // The warehouse ships with a sales rep; the rep confirms the hand-over.
  await login(page, WM);
  await page.goto(`/stock-requests/${sr.id}`);
  await page.getByRole("button", { name: "Ship", exact: true }).click();
  const ship = page.getByRole("dialog", { name: `Ship ${sr.number}` });
  await ship.getByText("Sales representative", { exact: true }).click();
  const repApi = await apiAs(SR);
  const me = await json<{ full_name: string }>(await repApi.get("/api/auth/me"));
  await ship.getByRole("combobox", { name: /Sales representative/ }).selectOption({ label: me.full_name });
  await ship.getByRole("button", { name: "Create shipment" }).click();
  await expect(ship).toBeHidden();
  const detail = await json<{ shipments: { id: number }[] }>(await repApi.get(`/api/stock-requests/${sr.id}`));
  const confirmed = await json<{ status: string }>(await repApi.post(`/api/stock-requests/${sr.id}/shipments/${detail.shipments[0].id}/confirm`,
    { data: { received_by_name: "Shop owner", notes: "Handed over" } }));
  expect(confirmed.status).toBe("DELIVERED");

  // A partial approval: the dealer sees the kind message and never the internal reason.
  const sr2 = await json<{ id: number; number: string; lines: { id: number }[] }>(await dealer.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 50 }] } }));
  const wm = await apiAs(WM);
  await json(await wm.post(`/api/stock-requests/${sr2.id}/decision`, { data: {
    lines: [{ line_id: sr2.lines[0].id, approve_qty: 2, remainder: "REJECT", notes: "Internal: dealer on credit hold" }],
    approval: { method: "STANDARD", comments: "Standard top-up only" } } }));
  const mine = await json<{ review_notes: string }>(await dealer.get(`/api/stock-requests/${sr2.id}`));
  expect(mine.review_notes).toContain("Sorry, we couldn't deliver your order this time");
  expect(JSON.stringify(mine)).not.toContain("credit hold");
});

test("(8) replenishment: a rep raises it, the warehouse approves with details, packs and ships with the rep, the rep confirms delivery", async ({ page }) => {
  const f = await setup({ resellerStock: 0, target: 6, warehouseStock: 10, tag: "REP" });
  const repApi = await apiAs(SR);
  const me = await json<{ full_name: string }>(await repApi.get("/api/auth/me"));

  // The rep raises the request with a note for the approver.
  await login(page, SR);
  await page.goto("/backorders");
  await page.getByRole("button", { name: "Manual request" }).click();
  const form = page.getByRole("dialog", { name: "Manual replenishment request" });
  await selectByPrefix(form.getByLabel("Dealer location"), f.locationCode);
  await pickProduct(form, f.sku);
  await form.getByLabel("Quantity").fill("3");
  await form.getByLabel("Reason").fill("Shop is running low");
  await form.getByLabel("Note for the approver").fill("Customer collecting Friday");
  await form.getByRole("button", { name: "Create request" }).click();
  await expect(form).toBeHidden();
  const [req] = await json<{ id: number; number: string }[]>(await repApi.get(`/api/replenishment/requests?reseller_id=${f.resellerId}`));

  // The Warehouse Manager was told, approves with the details, prints the pick sheet and marks it ready.
  await login(page, WM);
  const wm = await apiAs(WM);
  const notes = await json<{ title: string; body: string }[]>(await wm.get("/api/notifications"));
  expect(notes.find((n) => n.title === `${req.number} is waiting for approval`)?.body).toContain("Customer collecting Friday");
  await page.goto(`/replenishment/${req.id}`);
  await expect(page.getByText("waiting for approval")).toBeVisible();
  await expect(page.getByRole("link", { name: "Print pick sheet" })).toBeVisible();
  await page.getByRole("button", { name: "Approve…" }).click();
  const approve = page.getByRole("dialog", { name: `Approve ${req.number}` });
  await approve.getByLabel("How was it approved").selectOption("PHONE");
  await approve.getByLabel("Spoke to").fill("Shop manager");
  await approve.getByLabel("Comments").fill("Agreed on the phone");
  await approve.getByRole("button", { name: "Approve and reserve" }).click();
  await expect(approve).toBeHidden();
  await expect(page.getByText("Phone call")).toBeVisible();   // the Approval card
  await expect(page.getByText("Shop manager", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mark ready for shipment" }).click();
  await expect(page.getByRole("button", { name: "Mark ready for shipment" })).toHaveCount(0);
  await page.goto("/replenishment?tab=dispatch");
  await expect(page.getByRole("row", { name: new RegExp(req.number) }).getByText("Ready", { exact: true })).toBeVisible();

  // Ship with the rep.
  await page.goto(`/replenishment/${req.id}`);
  await page.getByRole("button", { name: "Ship", exact: true }).click();
  const ship = page.getByRole("dialog", { name: `Ship ${req.number}` });
  await ship.getByText("Sales representative", { exact: true }).click();
  await ship.getByRole("combobox", { name: /Sales representative/ }).selectOption({ label: me.full_name });
  await ship.getByRole("button", { name: "Create shipment" }).click();
  await expect(ship).toBeHidden();
  await expect(page.getByText(/To be confirmed by the dealer or/)).toBeVisible();   // not the WM's to confirm

  // The rep confirms the hand-over on the request.
  await login(page, SR);
  await page.goto(`/replenishment/${req.id}`);
  await page.getByRole("button", { name: "Confirm delivery" }).click();
  const confirm = page.getByRole("dialog", { name: /Confirm delivery of/ });
  await confirm.getByLabel("Received by").fill("Shop owner");
  await confirm.getByLabel("Hand-over notes").fill("Handed over at the counter");
  await confirm.getByRole("button", { name: "Confirm delivery" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.getByText("Shop owner", { exact: true })).toBeVisible();
  const done = await json<{ status: string; qty_delivered: number }>(await wm.get(`/api/replenishment/requests/${req.id}`));
  expect(done).toMatchObject({ status: "FULFILLED", qty_delivered: 3 });
  expect((await json<{ balanced: boolean }>(await wm.get("/api/inventory/reconciliation"))).balanced).toBe(true);
});

test("(9) transfer carried by a rep: pick-up arranged on approval, rep collects and delivers, delivery note", async ({ page }) => {
  const source = await setup({ resellerStock: 4, warehouseStock: 0, tag: "TRS" });
  const dest = await setup({ resellerStock: 0, warehouseStock: 0, tag: "TRD" });
  const wm = await apiAs(WM);
  const repApi = await apiAs(SR);
  const me = await json<{ full_name: string }>(await repApi.get("/api/auth/me"));
  const t = await json<{ id: number; number: string }>(await wm.post("/api/transfers", { data: {
    destination_location_id: dest.locationId, product_id: source.productId, quantity: 2, reason: "Customer waiting" } }));

  // The warehouse approves, chooses the source and arranges the pick-up with the rep in the same step.
  await login(page, WM);
  await page.goto(`/transfers/${t.id}`);
  await page.getByRole("button", { name: "Approve & choose source" }).click();
  const approve = page.getByRole("dialog", { name: "Approve transfer" });
  await selectByPrefix(approve.getByLabel("Source location"), source.locationCode);
  await approve.getByLabel("Arrange the pick-up now").check();
  await approve.getByRole("combobox", { name: /Sales representative/ }).selectOption({ label: me.full_name });
  await approve.getByRole("button", { name: "Approve & reserve" }).click();
  await expect(approve).toBeHidden();
  await expect(page.getByText(`Sales representative · ${me.full_name}`).first()).toBeVisible();
  await expect(page.getByText(`To be collected by ${me.full_name}`)).toBeVisible();     // not the warehouse's to record
  const notes = await json<{ title: string; body: string }[]>(await repApi.get("/api/notifications"));
  expect(notes.find((n) => n.title.startsWith(`Please collect ${t.number}`))?.body).toMatch(/^Collect from E2E Reseller TRS.+ and deliver to E2E Reseller TRD/);

  // The rep sees it to collect, records who handed it over, then confirms the delivery.
  await login(page, SR);
  await expect(page.getByRole("link", { name: new RegExp(`${t.number}.*Transfer · to collect`) })).toBeVisible();
  await page.goto(`/transfers/${t.id}`);
  await page.getByRole("button", { name: "Record collection" }).click();
  const collect = page.getByRole("dialog", { name: "Record collection from source" });
  await collect.getByLabel("Collected from").fill("Sam at the source shop");
  await collect.getByRole("button", { name: "Record collection" }).click();
  await expect(collect).toBeHidden();
  await expect(page.getByText("Handed over by Sam at the source shop")).toBeVisible();
  await page.getByRole("button", { name: "Confirm delivery" }).click();
  const confirm = page.getByRole("dialog", { name: "Confirm delivery at destination" });
  await confirm.getByLabel("Received by").fill("Dest owner");
  await confirm.getByLabel("Hand-over notes").fill("Handed over at the counter");
  await confirm.getByRole("button", { name: "Confirm receipt" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.getByRole("link", { name: "Delivery note (PDF)" })).toBeVisible();

  const done = await json<{ status: string; qty_received: number }>(await wm.get(`/api/transfers/${t.id}`));
  expect(done).toMatchObject({ status: "COMPLETED", qty_received: 2 });
  const pdf = await wm.get(`/api/transfers/${t.id}/delivery-note.pdf`);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
});

test("(10) sale → invoice record → Xero number; the WM sees only 'Invoiced ✓', the FM sees the number", async ({ page }) => {
  const f = await setup({ resellerStock: 4, warehouseStock: 0, tag: "XRO" });
  const dealer = await dealerApi(f.resellerId);
  const rmApi = await apiAs(RM);
  const { business_name: name } = await json<{ business_name: string }>(await rmApi.get(`/api/resellers/${f.resellerId}`));
  const sale = await json<{ id: number; number: string }>(await dealer.post("/api/sales", { data: {
    location_id: f.locationId, sale_date: today(), lines: [{ product_id: f.productId, quantity: 2 }] } }));
  const xero = `INV-X-1001-${stamp()}`;

  // The Relationship Manager creates the invoice record and marks it invoiced in Xero.
  await login(page, RM);
  await page.goto("/invoices");
  await page.getByRole("row", { name: new RegExp(name) }).getByRole("button", { name: /^Select \d+ line/ }).click();
  await page.getByRole("button", { name: /^Create invoice record/ }).click();
  await page.waitForURL(/\/invoices\/\d+$/);
  await expect(page.getByText("Invoice summary for Xero")).toBeVisible();
  await expect(page.getByRole("cell", { name: sale.number })).toBeVisible();
  await page.getByRole("button", { name: "Mark as invoiced in Xero" }).click();
  const mark = page.getByRole("dialog", { name: "Mark as invoiced in Xero" });
  await mark.getByLabel("Xero invoice number").fill(xero);
  await mark.getByRole("button", { name: "Mark as invoiced" }).click();
  await expect(mark).toBeHidden();
  await expect(page.getByText(xero)).toBeVisible();

  // The Warehouse Manager sees that it is invoiced, never the number.
  await login(page, WM);
  await page.goto(`/sales?sale=${sale.id}`);
  const drawer = page.getByRole("dialog", { name: `Sale ${sale.number}` });
  await expect(drawer.getByText("Invoiced ✓").first()).toBeVisible();
  await expect(page.getByText(xero)).toHaveCount(0);

  // The Finance Manager sees the Xero number on the sale.
  await newStaffUser(page, "FINANCE_MANAGER", "Fay Finance");
  await page.goto(`/sales?sale=${sale.id}`);
  await expect(page.getByRole("dialog", { name: `Sale ${sale.number}` }).getByText(`Xero no. ${xero}`)).toBeVisible();
});

test("(11) stock check: the dealer sees who to call and asks for a re-check; the rep starts the re-count", async ({ page }) => {
  const f = await setup({ resellerStock: 5, warehouseStock: 0, tag: "STK" });
  const rm = await apiAs(RM);
  const email = `dealer-stk-${stamp()}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: "E2E Count Dealer", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));
  const sr = await apiAs(SR);
  const st = await json<{ id: number; number: string }>(await sr.post("/api/stocktakes", { data: {
    location_id: f.locationId, count_date: today(), counts: [{ product_id: f.productId, counted_qty: 3 }] } }));
  await json(await sr.post(`/api/stocktakes/${st.id}/submit`));
  const wmMe = await json<{ full_name: string }>(await (await apiAs(WM)).get("/api/auth/me"));

  // The dealer: 5 days to find them, contacts on the page, "I found them, please re-check".
  await firstSignIn(page, email);
  await page.goto(`/stocktakes/${st.id}`);
  await expect(page.getByText(/You have 5 days to find them/)).toBeVisible();
  const contacts = page.locator("section", { hasText: "Questions? Contact us" });
  await expect(contacts.getByText(wmMe.full_name).first()).toBeVisible();
  await expect(contacts.getByText("Warehouse Manager").first()).toBeVisible();
  await page.getByRole("button", { name: "I found them, please re-check" }).click();
  const recheck = page.getByRole("dialog", { name: "I found them, please re-check" });
  await recheck.getByLabel("Note").fill("They were in the back store");
  await recheck.getByRole("button", { name: "Ask for a re-check" }).click();
  await expect(recheck).toBeHidden();
  await expect(page.getByText("Re-check requested", { exact: true })).toBeVisible();
  await expect(page.getByText(/They were in the back store/)).toBeVisible();

  // The rep starts the re-count: a new draft for the same shop, linked to the original.
  await login(page, SR);
  await page.goto(`/stocktakes/${st.id}`);
  await page.getByRole("button", { name: "Start re-count" }).click();
  await page.getByRole("dialog", { name: "Start re-count" }).getByRole("button", { name: "Start re-count" }).click();
  await page.waitForURL((u) => /\/stocktakes\/\d+$/.test(u.pathname) && !u.pathname.endsWith(`/${st.id}`));
  await expect(page.getByText(`This is a re-count of ${st.number}.`)).toBeVisible();
  await page.goto(`/stocktakes/${st.id}`);
  await expect(page.getByText(/Re-counted in STK-/)).toBeVisible();
  expect((await balance(f.locationId, f.productId)).available).toBe(5);   // the hold is released
});

test("(12) report by dealer by SKU loads and downloads", async ({ page }) => {
  const f = await setup({ resellerStock: 6, warehouseStock: 0, tag: "RPT" });
  const dealer = await dealerApi(f.resellerId);
  await json(await dealer.post("/api/sales", { data: { location_id: f.locationId, sale_date: today(), lines: [{ product_id: f.productId, quantity: 2 }] } }));
  const { business_name: name, account_ref: ref } = await json<{ business_name: string; account_ref: string }>(
    await (await apiAs(RM)).get(`/api/resellers/${f.resellerId}`));

  await login(page, RM);
  await page.goto("/reports");
  await page.getByRole("tab", { name: "By dealer by SKU" }).click();
  await page.getByLabel("Dealer").selectOption({ label: `${ref} — ${name}` });
  const card = page.locator("section", { hasText: name }).first();
  const row = card.getByRole("row", { name: new RegExp(f.sku) });
  await expect(row).toBeVisible();
  // On hand 4, available 4, held 0, on the way 0, waiting 2 (the replacement), sold 2, invoiced 0, not yet invoiced 2.
  await expect(row.getByRole("cell")).toHaveText([/E2E/, new RegExp(f.sku), "4", "4", "0", "0", "2", "2", "0", "2"]);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download Excel" }).click();
  expect((await download).suggestedFilename()).toMatch(/^TyreGrow-by-dealer-by-SKU-\d{8}-\d{8}\.xlsx$/);
  await expect(page.getByText(/\$\s?\d/)).toHaveCount(0);
});

test("(13) rep handover: the new rep takes over and the old rep can't sign in", async ({ page, request }) => {
  const f = await setup({ resellerStock: 2, warehouseStock: 0, tag: "HND" });
  const rm = await apiAs(RM);
  const oldEmail = `old-rep-${stamp()}@e2e.example.com`;
  const old = await json<{ id: number; full_name: string }>(await rm.post("/api/users", { data: {
    email: oldEmail, full_name: `Olly Leaving ${stamp()}`, password: "leaving-pass-12", role: "SALES_REP" } }));
  await json(await rm.patch(`/api/resellers/${f.resellerId}`, { data: { sales_rep_user_id: old.id } }));

  // The Relationship Manager adds the new rep, who takes over everything from the one leaving.
  await login(page, RM);
  await page.goto("/admin");
  await page.getByRole("button", { name: "New user" }).click();
  const form = page.getByRole("dialog", { name: "New user" });
  const newEmail = `new-rep-${stamp()}@e2e.example.com`;
  await form.getByLabel("Email").fill(newEmail);
  await form.getByLabel("Full name").fill("Nia Newrep");
  await form.getByLabel("Role").selectOption("SALES_REP");
  await form.getByLabel("Password").fill("first-pass-1234");
  await form.getByLabel("Is this person replacing someone?").check();
  await form.getByLabel(/^Who/).selectOption({ label: `${old.full_name} · looks after 1 dealer(s)` });
  await form.getByLabel(/Take over everything/).check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toBeHidden();

  const dealer = await json<{ sales_rep_user_id: number; sales_rep_name: string }>(await rm.get(`/api/resellers/${f.resellerId}`));
  expect(dealer.sales_rep_name).toBe("Nia Newrep");
  await expect(page.getByRole("row", { name: new RegExp(old.full_name) }).getByText("Inactive")).toBeVisible();
  // The person who left can no longer sign in.
  const res = await request.post("/api/auth/login", { data: { email: oldEmail, password: "leaving-pass-12" } });
  expect(res.status()).toBe(401);
});
