import { expect, test } from "@playwright/test";
import { apiAs, balance, dealerDetails, json, login, pickProduct, RM, selectByPrefix, setup, SR, WM } from "./helpers";

test("Scenario 1 — sale, replenishment dispatch and receipt, no duplicate invoice", async ({ page }) => {
  const f = await setup({ tag: "S1", resellerStock: 20, target: 20, warehouseStock: 50 });

  // Sales rep records the confirmed sale.
  await login(page, SR);
  await page.goto("/sales");
  await page.getByRole("button", { name: "Record sale" }).click();
  const dialog = page.getByRole("dialog");
  await selectByPrefix(dialog.getByLabel("Dealer location"), f.locationCode);
  await pickProduct(dialog, f.sku);
  await dialog.getByLabel("Quantity").fill("8");
  await dialog.getByRole("button", { name: "Record sale" }).click();
  await expect(page.getByText(/Replenishment raised: REP-\d+ \(8, Allocated\)/)).toBeVisible();
  expect((await balance(f.locationId, f.productId)).on_hand).toBe(12);

  // Warehouse operator dispatches the allocated stock.
  await login(page, WM);
  await page.goto("/replenishment");
  const card = page.locator("section", { hasText: f.locationCode });
  await card.getByRole("button", { name: /Dispatch 8 unit/ }).click();
  await expect(page.getByText(new RegExp(`Dispatched DEL-\\d+ to ${f.locationCode}: 8 unit`))).toBeVisible();

  // Sales rep confirms receipt at the reseller.
  await login(page, SR);
  await page.goto("/replenishment");
  await page.getByRole("tab", { name: "Deliveries" }).click();
  await page.locator("tr", { hasText: f.locationCode }).getByRole("button", { name: "Confirm receipt" }).click();
  const receipt = page.getByRole("dialog");
  // A Sales Rep handing stock over records who took it and a short note.
  await expect(receipt.getByRole("button", { name: "Confirm receipt" })).toBeDisabled();
  await receipt.getByLabel("Received by").fill("Ravi (owner)");
  await receipt.getByLabel("Hand-over notes").fill("Handed over at the counter");
  await receipt.getByRole("button", { name: "Confirm receipt" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Filter").selectOption({ label: "All" });
  await expect(page.locator("tr", { hasText: f.locationCode }).getByText("Ravi (owner)")).toBeVisible();

  expect((await balance(f.locationId, f.productId)).on_hand).toBe(20);
  const fin = await apiAs(RM);
  const uninvoiced = await json<{ quantity: number }[]>(await fin.get(`/api/invoices/uninvoiced?reseller_id=${f.resellerId}`));
  expect(uninvoiced.map((u) => u.quantity)).toEqual([8]);          // exactly one chargeable sale line
  expect(await json<unknown[]>(await fin.get(`/api/invoices?reseller_id=${f.resellerId}`))).toEqual([]); // no invoice from delivery
});

test("Scenario 2 — stockout backorder stays open until supply is received and allocated", async ({ page }) => {
  const f = await setup({ tag: "S2", resellerStock: 10, target: 10, warehouseStock: 0 });
  const rep = await apiAs(SR);
  await json(await rep.post("/api/sales", { data: { location_id: f.locationId, sale_date: new Date().toISOString().slice(0, 10), lines: [{ product_id: f.productId, quantity: 4 }] } }));

  await login(page, RM);
  await page.goto("/backorders");
  const row = page.locator("tr", { hasText: f.sku });
  await expect(row).toContainText("Sale");
  await expect(row.locator("td").nth(7)).toHaveText("4");            // awaiting supply

  // Warehouse receives supplier stock without a PO; the backorder is not closed by the receipt.
  await login(page, WM);
  await page.goto("/purchasing");
  await page.getByRole("button", { name: "Receive without PO" }).click();
  const dialog = page.getByRole("dialog");
  await pickProduct(dialog, f.sku);
  await dialog.getByLabel("Received").fill("6");
  await dialog.getByRole("button", { name: "Post receipt" }).click();
  await expect(page.getByText(/open backorder\(s\) are waiting for these SKUs/)).toBeVisible();

  // Allocation is proposed and confirmed by a person.
  await page.goto("/backorders");
  await page.getByRole("tab", { name: "Allocate received stock" }).click();
  const prop = page.locator("tr", { hasText: f.sku });
  await expect(prop.getByRole("spinbutton")).toHaveValue("4");
  await page.getByRole("button", { name: "Confirm allocations" }).click();
  await expect(page.getByText(/Reserved stock for \d+ request/)).toBeVisible();
  expect((await balance(f.warehouseId, f.productId)).reserved).toBe(4);
});

test("Scenario 3 — guided inter-reseller transfer creates a source obligation and no invoice", async ({ page }) => {
  const source = await setup({ tag: "S3A", resellerStock: 6, target: 6, warehouseStock: 0 });
  const mgr = await apiAs(RM);
  // Destination reseller for the same SKU.
  const destRun = Date.now().toString(36).toUpperCase();
  const dest = await json<{ id: number; locations: { id: number; code: string }[] }>(await mgr.post("/api/resellers", { data: {
    ...(await dealerDetails(mgr, destRun)), account_ref: `D${destRun}`, business_name: "E2E Destination",
    locations: [{ code: `D${destRun}-MAIN`, name: "E2E Destination Main", address_line1: "2 Test Street", city: "Hamilton" }] } }));
  const destLoc = dest.locations[0];

  await login(page, RM);
  await page.goto(`/transfers/new?destination=${destLoc.id}`);
  await pickProduct(page, source.sku);
  await page.getByLabel("Quantity").fill("2");
  await page.getByLabel("Reason").fill("Customer needs a matching pair today");
  await page.getByRole("button", { name: "Check availability" }).click();
  await expect(page.getByText("Warehouse available: 0")).toBeVisible();
  await page.getByRole("radio", { name: `Select ${source.locationCode}` }).check();
  await page.getByRole("button", { name: `Use ${source.locationCode}` }).click();
  await expect(page.getByText("Owed replacement")).toBeVisible();
  await page.getByRole("button", { name: "Approve transfer & reserve stock" }).click();

  await expect(page.getByRole("heading", { name: /Transfer TRF-\d+/ })).toBeVisible();
  expect((await balance(source.locationId, source.productId)).reserved).toBe(2);
  await page.getByRole("button", { name: "Record collection" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Record collection" }).click();
  await expect(page.getByText(/REP-\d+/).first()).toBeVisible();          // source obligation raised
  await page.getByRole("button", { name: "Confirm receipt" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm receipt" }).click();
  await expect(page.getByRole("heading", { name: /Completed/ })).toBeVisible();

  expect((await balance(source.locationId, source.productId)).on_hand).toBe(4);
  expect((await balance(destLoc.id, source.productId)).on_hand).toBe(2);
  const reqs = await json<{ reason: string; qty_awaiting_supply: number }[]>(await mgr.get(`/api/replenishment/requests?reseller_id=${source.resellerId}`));
  expect(reqs.map((r) => [r.reason, r.qty_awaiting_supply])).toEqual([["TRANSFER", 2]]);
  const fin = await apiAs(RM);
  for (const rid of [source.resellerId, dest.id]) {
    expect(await json<unknown[]>(await fin.get(`/api/invoices/uninvoiced?reseller_id=${rid}`))).toEqual([]);
  }
});

test("Reseller users change their temporary password, see only their own account and can report a sale", async ({ page }) => {
  const f = await setup({ tag: "RS", resellerStock: 6, target: 6, warehouseStock: 10 });
  const other = await setup({ tag: "RX", resellerStock: 2, warehouseStock: 0 });
  const rm = await apiAs(RM);   // the Relationship Manager administers user logins
  const email = `reseller.${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: "E2E Reseller User", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));

  // First sign-in forces a personal password.
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Choose your own password" })).toBeVisible();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill("my-reseller-pass-2");
  await page.getByLabel("Confirm new password").fill("my-reseller-pass-2");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();

  // Reseller navigation only.
  await expect(page.getByRole("link", { name: "My account" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Report Sale" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Warehouse" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Reports" })).toHaveCount(0);
  await page.goto(`/resellers/${other.resellerId}`);
  await expect(page.getByText("Dealer not found")).toBeVisible();

  // Report a sale for its own (only) location.
  await page.goto("/sales?new=1");
  const dialog = page.getByRole("dialog");
  await pickProduct(dialog, f.sku);
  await dialog.getByLabel("Quantity").fill("2");
  await dialog.getByRole("button", { name: "Report sale" }).click();
  await expect(page.getByText(/Recorded SAL-\d+: 2 unit/)).toBeVisible();
  expect((await balance(f.locationId, f.productId)).on_hand).toBe(4);

  // My Sales shows what was sold this month.
  await page.getByRole("link", { name: "My Sales" }).click();
  await expect(page.getByRole("heading", { name: "My sales" })).toBeVisible();
  await expect(page.locator("tr", { hasText: f.sku }).first()).toBeVisible();

  // Direct API access to another reseller is refused.
  const me = await apiAs(email, "my-reseller-pass-2");
  expect((await me.get(`/api/resellers/${other.resellerId}`)).status()).toBe(404);
  expect((await me.get(`/api/reports/resellers/${other.resellerId}/transactions`)).status()).toBe(404);
  expect((await me.get("/api/reports/warehouse-availability")).status()).toBe(403);
  expect((await me.post("/api/sales", { data: { location_id: other.locationId, sale_date: new Date().toISOString().slice(0, 10), source: "RESELLER_REPORT", lines: [{ product_id: other.productId, quantity: 1 }] } })).status()).toBe(404);
});

test("Scenario 4 — consignment stock request: create, partially approve, ship and confirm delivery", async ({ page }) => {
  const f = await setup({ tag: "S4", resellerStock: 0, warehouseStock: 3 });

  // Sales rep raises a multi-SKU request on behalf of the reseller (one SKU here).
  await login(page, SR);
  await page.goto("/stock-requests/new");
  await selectByPrefix(page.getByLabel("Dealer location"), f.locationCode);
  await pickProduct(page, f.sku);
  await page.getByLabel("Quantity", { exact: true }).fill("5");
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByRole("heading", { name: /SRQ-\d+/ })).toBeVisible();
  await expect(page.getByText("Submitted", { exact: true }).first()).toBeVisible();
  const url = page.url();

  // Relationship Manager (Central Team) sees it pending and approves what is available; the rest is backordered.
  await login(page, RM);
  await expect(page.getByRole("button", { name: /Notifications, \d+ unread/ })).toBeVisible();
  await page.goto("/stock-requests/pending");
  await page.locator("tr", { hasText: f.locationCode.split("-")[0] }).first().click();
  await page.waitForURL(url);
  await page.getByRole("button", { name: "Approve…" }).click();
  const decide = page.getByRole("dialog");
  await expect(decide.getByLabel(`Approve quantity for ${f.sku}`)).toHaveValue("3");
  await decide.getByRole("button", { name: "Partially approve" }).click();
  // Approval details (1.11, finding 17): how it was agreed, who was spoken to, a comment.
  const details = page.getByRole("dialog", { name: "Approval details" });
  await details.getByLabel("How was it approved").selectOption("PHONE");
  await details.getByLabel("Spoke to").fill("Dealer owner");
  await details.getByLabel("Comments").fill("Agreed by phone; rest when stock arrives");
  await details.getByRole("button", { name: "Confirm approval" }).click();
  await expect(page.getByText("Partially approved", { exact: true }).first()).toBeVisible();
  expect((await balance(f.warehouseId, f.productId)).reserved).toBe(3);

  // Warehouse Manager ships with carrier and tracking.
  await login(page, WM);
  await page.goto(url);
  await page.getByRole("button", { name: "Mark ready for shipment" }).click();
  await expect(page.getByText("Ready for shipment", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Ship", exact: true }).click();
  const ship = page.getByRole("dialog");
  await ship.getByLabel("Carrier").fill("StarTrack");
  await ship.getByLabel("Tracking number").fill("ST-E2E-1");
  await ship.getByRole("button", { name: "Create shipment" }).click();
  await expect(page.getByText("ST-E2E-1", { exact: true })).toBeVisible();

  // Sales rep confirms the delivery at the reseller.
  await login(page, SR);
  await page.goto(url);
  await page.getByRole("button", { name: "Confirm delivery" }).click();
  const confirm = page.getByRole("dialog");
  await confirm.getByLabel("Delivery reference").fill("POD-1");
  await confirm.getByLabel("Received by").fill("Shop owner");
  await confirm.getByLabel("Hand-over notes").fill("Owner signed the docket");
  await confirm.getByRole("button", { name: "Confirm delivery" }).click();
  await expect(page.getByText("POD-1", { exact: true })).toBeVisible();
  expect((await balance(f.locationId, f.productId)).on_hand).toBe(3);
});

test("Scenario 5 — stock check shortage: dealer has the tyres not found invoiced; invoice record and replacement follow", async ({ page }) => {
  const f = await setup({ tag: "S5", resellerStock: 5, warehouseStock: 5 });
  const rm = await apiAs(RM);   // the Relationship Manager administers user logins
  const email = `reseller.s5.${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: "E2E Stockcheck Reseller", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));

  // The sales rep counts 3 of the expected 5 and submits: the 2 missing tyres wait for the reseller.
  const sr = await apiAs(SR);
  const st = await json<{ id: number; number: string }>(await sr.post("/api/stocktakes", { data: {
    location_id: f.locationId, count_date: new Date().toISOString().slice(0, 10), counts: [{ product_id: f.productId, counted_qty: 3 }] } }));
  const submitted = await json<{ status: string }>(await sr.post(`/api/stocktakes/${st.id}/submit`));
  expect(submitted.status).toBe("AWAITING_RESELLER");

  // The relationship manager's dashboard highlights it.
  await login(page, RM);
  const rmAlert = page.locator("section", { hasText: "Stock checks awaiting dealer confirmation" });
  await expect(rmAlert.getByRole("link", { name: st.number })).toBeVisible();

  // The reseller signs in, sees the action on their dashboard and confirms both tyres as sold.
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("temporary-pass-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill("temporary-pass-1");
  await page.getByLabel("New password", { exact: true }).fill("my-reseller-pass-2");
  await page.getByLabel("Confirm new password").fill("my-reseller-pass-2");
  await page.getByRole("button", { name: "Save new password" }).click();
  // 1.11 (findings 28–30): no "missing"; tyres not found are invoiced as sold on an ordinary invoice record.
  const action = page.locator("section", { hasText: "Action needed: tyres not found at a stock check" });
  await action.getByRole("link", { name: st.number }).click();
  await page.getByRole("button", { name: "Not found, invoice them now" }).click();
  await expect(page.getByText(/invoiced as sold: invoice record INV-\d+/)).toBeVisible();
  expect((await balance(f.locationId, f.productId)).on_hand).toBe(3);

  // The relationship manager sees who to invoice; the replacement waits for picking.
  const reqs = await json<{ reseller_id: number; qty_required: number; reason: string }[]>(await rm.get(`/api/replenishment/requests?reseller_id=${f.resellerId}`));
  expect(reqs.map((r) => [r.reason, r.qty_required])).toEqual([["SALE", 2]]);
  await login(page, RM);
  await page.goto("/invoices");
  await expect(page.getByRole("heading", { name: "Who to invoice" })).toBeVisible();
});

test("Scenario 6 — existing reseller with initial stock, cash sale, shipping with a sales rep and delivery note", async ({ page }) => {
  const f = await setup({ tag: "S6", resellerStock: 0, warehouseStock: 10 });
  const run = Date.now().toString(36).toUpperCase();

  // The relationship manager adds an existing reseller together with the stock they hold today.
  await login(page, RM);
  await page.goto("/resellers?new=1");
  const form = page.getByRole("dialog");
  await form.getByText(/^Existing .+ dealer$/).click();
  await form.getByLabel(/^Business name/).fill(`Existing Tyres ${run}`);   // the account reference is generated (D4)
  await form.getByLabel("Contact name").fill("Eve Existing");
  await form.getByLabel(/^Email/).fill(`ex-${run.toLowerCase()}@e2e.example.com`);
  await form.getByLabel(/^Phone/).fill("09 555 0199");
  await form.getByLabel("Sales representative").selectOption({ index: 1 });
  await form.getByLabel("Billing address").fill("5 Existing Road, Auckland");
  await form.getByLabel("Shop 1 delivery address").fill("5 Existing Road");   // the shop code is generated
  await form.getByLabel("Shop 1 city").fill("Auckland");
  await pickProduct(form, f.sku);
  await form.getByLabel("Quantity held, line 1").fill("4");
  await form.getByRole("button", { name: "Create dealer and add stock" }).click();
  // The dealer's login is created too (D7): its temporary password is shown once.
  await expect(page.getByTestId("temporary-password")).toHaveText(/^[A-Za-z2-9]{12}$/);
  await page.getByRole("button", { name: "Done — open the dealer" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Existing Tyres ${run}`) })).toBeVisible();
  const rm = await apiAs(RM);
  const created = (await json<{ id: number; account_ref: string; business_name: string; locations: { id: number }[] }[]>(await rm.get("/api/resellers"))).find((r) => r.business_name === `Existing Tyres ${run}`)!;
  const detail = await json<{ locations: { id: number }[] }>(await rm.get(`/api/resellers/${created.id}`));
  expect((await balance(detail.locations[0].id, f.productId)).on_hand).toBe(4);

  // The warehouse manager sells two tyres from the warehouse (non-consignment sale).
  await login(page, WM);
  await page.goto("/sales");
  await page.getByRole("button", { name: "Record sale" }).click();
  const sale = page.getByRole("dialog");
  await expect(sale.getByLabel("Dealer location")).toHaveValue("cash");
  await sale.getByLabel("Customer name").fill("Corner Garage");
  await pickProduct(sale, f.sku);
  await sale.getByLabel("Quantity").fill("2");
  await sale.getByRole("button", { name: "Record sale" }).click();
  // 1.11 (D6, D12): a non-consignment sale; the warehouse sees that an invoice record exists, not its number.
  await expect(page.getByText(/Non-consignment sale from the warehouse; invoice record created for Corner Garage/)).toBeVisible();
  expect((await balance(f.warehouseId, f.productId)).on_hand).toBe(8);

  // A replacement shipped with the sales rep; the rep confirms; the delivery note PDF is available.
  const wm = await apiAs(WM);
  const req = await json<{ id: number; qty_allocated: number }>(await rm.post("/api/replenishment/requests", { data: {
    location_id: f.locationId, product_id: f.productId, quantity: 3, reason: "E2E top-up" } }));
  expect(req.qty_allocated).toBe(3);
  const staff = await json<{ id: number; role: string }[]>(await wm.get("/api/staff"));
  const repId = staff.find((u) => u.role === "SALES_REP")!.id;
  const del = await json<{ id: number; carried_by: string }>(await wm.post("/api/replenishment/deliveries", { data: {
    to_location_id: f.locationId, lines: [{ request_id: req.id }], shipping_method: "SALES_REP", carried_by_user_id: repId } }));
  expect(del.carried_by).toBeTruthy();
  const sr = await apiAs(SR);
  // Carried by the rep: the warehouse cannot confirm it; the rep records who received it.
  expect((await wm.post(`/api/replenishment/deliveries/${del.id}/receive`, { data: { lines: [] } })).status()).toBe(403);
  await json(await sr.post(`/api/replenishment/deliveries/${del.id}/receive`, { data: {
    lines: [], received_by_name: "Shop owner", notes: "Handed over at the counter" } }));
  const pdf = await sr.get(`/api/replenishment/deliveries/${del.id}/delivery-note.pdf`);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  await login(page, SR);
  await page.goto("/replenishment?tab=deliveries");
  await page.getByRole("combobox", { name: "Filter" }).selectOption("false");
  await expect(page.getByRole("link", { name: "Delivery note (PDF)" }).first()).toBeVisible();
});
