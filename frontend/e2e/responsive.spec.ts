import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { apiAs, dealerDetails, json, PASSWORD, RM, setup, SR, today, WM } from "./helpers";

// Phase 4: responsive smoke tests on a phone, a tablet in both orientations and a desktop. Touch devices are emulated
// (isMobile + hasTouch), so `pointer: coarse` styles apply as they do on real phones and tablets.

const DEVICES = [
  { name: "phone 390", width: 390, height: 844, touch: true },
  { name: "tablet portrait 820", width: 820, height: 1180, touch: true },
  { name: "tablet landscape 1180", width: 1180, height: 820, touch: true },
  { name: "desktop 1440", width: 1440, height: 900, touch: false },
];

/** Sign in without assuming the desktop sidebar (phones and portrait tablets use the menu button). */
async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/");
}

/** The page's own width, compared with the device width (on a phone an overflowing page widens the layout viewport,
 *  so innerWidth cannot be used). */
const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);

/** Size of the area that answers taps: the element itself or its touch-target pseudo-element, whichever is larger. */
const tapArea = (page: Page, selector: string) => page.locator(selector).first().evaluate((el) => {
  const r = el.getBoundingClientRect(), a = getComputedStyle(el, "::after");
  return { w: Math.max(r.width, parseFloat(a.width) || 0), h: Math.max(r.height, parseFloat(a.height) || 0) };
});

interface Records { stockRequestId: number; transferId: number; resellerId: number; replenishmentId: number; saleId: number; dealer: string; stocktakeId: number; finance: string;
  pickReplenishmentId: number; invoiceId: number }
let records: Records;

test.beforeAll(async () => {
  // A dealer with stock, a stock request and a transfer to another dealer, so list and detail pages have real rows
  // (long SKUs, several columns, header actions).
  const source = await setup({ tag: "RSP", resellerStock: 6, target: 6, warehouseStock: 4 });
  const rm = await apiAs(RM);
  const run = `R${Date.now().toString(36).toUpperCase()}`;
  const dest = await json<{ id: number; locations: { id: number }[] }>(await rm.post("/api/resellers", { data: {
    ...(await dealerDetails(rm, run)), account_ref: `D${run}`, business_name: `E2E Responsive ${run}`,
    locations: [{ code: `D${run}-MAIN`, name: `E2E Responsive ${run} Main`, address_line1: "3 Test Street", city: "Napier" }] } }));
  const sr = await json<{ id: number }>(await rm.post("/api/stock-requests", { data: {
    location_id: source.locationId, submit: true, lines: [{ product_id: source.productId, quantity: 1 }] } }));
  const transfer = await json<{ id: number }>(await rm.post("/api/transfers", { data: {
    destination_location_id: dest.locations[0].id, product_id: source.productId, quantity: 1, reason: "Responsive check" } }));
  const sale = await json<{ id: number; lines: { replenishment: { id: number }[] }[] }>(await rm.post("/api/sales", { data: {
    location_id: source.locationId, sale_date: today(), lines: [{ product_id: source.productId, quantity: 1 }] } }));
  // The replacement for that sale is reserved in the warehouse; the warehouse ships it (a delivery in transit).
  const wm = await apiAs(WM);
  await json(await wm.post("/api/replenishment/deliveries", { data: { to_location_id: source.locationId,
    lines: [{ request_id: sale.lines[0].replenishment[0].id, quantity: 1 }], shipping_method: "COURIER", carrier: "E2E Freight" } }));
  await wm.dispose();
  // A second sale: its replacement is reserved and waits to be picked.
  const toPick = await json<{ lines: { replenishment: { id: number }[] }[] }>(await rm.post("/api/sales", { data: { location_id: source.locationId, sale_date: today(),
    lines: [{ product_id: source.productId, quantity: 1 }] } }));
  // A dealer whose replacement cannot be supplied: a backorder.
  const short = await setup({ tag: "RSB", resellerStock: 3, target: 3, warehouseStock: 0 });
  await json(await rm.post("/api/sales", { data: { location_id: short.locationId, sale_date: today(),
    lines: [{ product_id: short.productId, quantity: 1 }] } }));
  // A draft invoice record for the source dealer, and a supplier order for the warehouse.
  const invoice = await json<{ id: number }>(await rm.post("/api/invoices", { data: { reseller_id: source.resellerId } }));
  await json(await rm.post("/api/purchasing/purchase-orders", { data: { supplier_name: "E2E Supplier", warehouse_location_id: source.warehouseId,
    expected_date: today(), lines: [{ product_id: source.productId, qty_ordered: 4 }] } }));
  // A completed stock check at the source dealer: everything counted.
  const onHand = (await json<{ product_id: number; on_hand: number }[]>(await rm.get(`/api/inventory/balances?location_id=${source.locationId}`)))
    .filter((b) => b.product_id === source.productId).reduce((n, b) => n + b.on_hand, 0);
  const st = await json<{ id: number }>(await rm.post("/api/stocktakes", { data: { location_id: source.locationId, count_date: today(),
    counts: [{ product_id: source.productId, counted_qty: onHand }] } }));
  await json(await rm.post(`/api/stocktakes/${st.id}/submit`));
  // A dealer login for the source dealer, with its own password already chosen.
  const dealerEmail = `rsp-shop-${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email: dealerEmail, full_name: "E2E Shop", password: "temporary-pass-1", role: "RESELLER", reseller_id: source.resellerId } }));
  await json(await rm.post("/api/feedback", { data: { page: "/products", feedback_type: "IMPROVEMENT", description: "Responsive check feedback" } }));
  // A Finance Manager login, also with its own password.
  const financeEmail = `rsp-fm-${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email: financeEmail, full_name: "E2E Finance", password: "temporary-pass-1", role: "FINANCE_MANAGER" } }));
  await rm.dispose();
  for (const email of [dealerEmail, financeEmail]) {
    const u = await apiAs(email, "temporary-pass-1");
    await json(await u.post("/api/auth/password", { data: { current_password: "temporary-pass-1", new_password: PASSWORD } }));
    await u.dispose();
  }
  records = { stockRequestId: sr.id, transferId: transfer.id, resellerId: source.resellerId,
    replenishmentId: sale.lines[0].replenishment[0].id, saleId: sale.id, dealer: dealerEmail, stocktakeId: st.id, finance: financeEmail,
    pickReplenishmentId: toPick.lines[0].replenishment[0].id, invoiceId: invoice.id };
});

for (const device of DEVICES) {
  test.describe(device.name, () => {
    test.use({ viewport: { width: device.width, height: device.height }, isMobile: device.touch, hasTouch: device.touch });

    test("no page scrolls sideways", async ({ page }) => {
      test.setTimeout(180_000);
      await signIn(page, RM);
      const routes = ["/", "/products", "/warehouse", "/consignment", "/inventory/allocation", "/inventory/movement",
        "/stock-requests/all", `/stock-requests/${records.stockRequestId}`, "/replenishment", "/backorders", "/transfers",
        `/transfers/${records.transferId}`, "/sales", "/invoices", "/resellers", `/resellers/${records.resellerId}`, "/purchasing",
        "/admin", "/stock-check", "/reports"];
      const wide: string[] = [];
      for (const route of routes) {
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("h1").first()).toBeVisible();
        const w = await pageWidth(page);
        if (w > device.width) wide.push(`${route}: ${w}px`);
      }
      expect(wide, `pages wider than ${device.width}px`).toEqual([]);
    });

    test("navigation is reachable and header controls are easy to tap", async ({ page }) => {
      await signIn(page, RM);
      const nav = page.getByRole("navigation", { name: "Main" });
      if (device.width < 1024) {
        await expect(nav).toBeHidden();
        await page.getByRole("button", { name: "Open menu" }).click();
        await expect(page.getByRole("dialog", { name: "Navigation" }).getByRole("link", { name: "Products" })).toBeVisible();
        if (device.touch) {
          const menu = await tapArea(page, 'button[aria-label="Close menu"]');
          expect(Math.min(menu.w, menu.h)).toBeGreaterThanOrEqual(44);
        }
        await page.getByRole("button", { name: "Close menu" }).click();
        if (device.touch) {
          const open = await tapArea(page, 'button[aria-label="Open menu"]');
          expect(Math.min(open.w, open.h)).toBeGreaterThanOrEqual(44);
        }
      } else {
        await expect(nav.getByRole("link", { name: "Products" })).toBeVisible();
      }
      if (device.touch) {
        for (const sel of ['button[aria-label^="Notifications"]', 'button[aria-label^="Account menu"]']) {
          const area = await tapArea(page, sel);
          expect(Math.min(area.w, area.h), sel).toBeGreaterThanOrEqual(44);
        }
      }
    });
  });
}

test.describe("phone notifications", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("a new notification docks at the bottom and does not cover the title or the main action", async ({ page }) => {
    test.setTimeout(90_000);
    const f = await setup({ resellerStock: 0, warehouseStock: 4, tag: "RNT" });
    await signIn(page, RM);
    await page.goto("/products");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);   // the first poll has set the baseline
    for (const d of await page.getByRole("button", { name: "Dismiss notification" }).all()) await d.click().catch(() => {});
    // A dealer submits a stock request: the Relationship Manager is notified.
    const rm = await apiAs(RM);
    const email = `rsp-dealer-${Date.now().toString(36)}@e2e.example.com`;
    await json(await rm.post("/api/users", { data: { email, full_name: "E2E Dealer", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));
    await rm.dispose();
    const dealer = await apiAs(email, "temporary-pass-1");
    const sr = await json<{ number: string }>(await dealer.post("/api/stock-requests", { data: {
      location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 1 }] } }));
    await dealer.dispose();
    const toast = page.getByRole("status", { name: "New notifications" }).locator("> div", { hasText: sr.number });
    await expect(toast).toBeVisible({ timeout: 25_000 });
    const t = (await toast.boundingBox())!;
    const title = (await page.locator("h1").first().boundingBox())!;
    const action = (await page.getByRole("button", { name: "Add product" }).boundingBox())!;
    const overlaps = (a: typeof t, b: typeof t) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
    expect(t.y + t.height).toBeGreaterThan(844 - 140);           // docked at the bottom
    expect(t.x).toBeGreaterThanOrEqual(0);
    expect(t.x + t.width).toBeLessThanOrEqual(390);
    expect(overlaps(t, title)).toBe(false);
    expect(overlaps(t, action)).toBe(false);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Phase 4B: shared table behaviours (representative screens: Products cards, Stock movement pinned scroll,
// Stock allocation scroll, Warehouse comfortable density, Invoices checkboxes).

const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };
const TABLET = { viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true };

/** axe-core on the given part of the page; returns violations as "rule: target" strings. */
async function axe(page: Page, include: string) {
  await page.addScriptTag({ path: path.join(process.cwd(), "node_modules/axe-core/axe.min.js") });
  return page.evaluate(async (sel) => {
    // @ts-expect-error axe is injected above
    const r = await window.axe.run({ include: [sel] }, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
    return r.violations.map((v: { id: string; nodes: { target: string[] }[] }) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  }, include);
}

test.describe("tables on a phone", () => {
  test.use(PHONE);

  test("Products shows cards: identifier and status first, fields, and a reachable Edit action", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    const table = page.getByRole("table", { name: "Products" });
    const card = table.getByRole("row").nth(1);
    await expect(card).toContainText("E2E-");                                              // real rows, not loading placeholders
    expect(await card.evaluate((el) => getComputedStyle(el).display)).toBe("grid");          // a card, not a table row
    expect(await table.locator("thead").evaluate((el) => el.getBoundingClientRect().height)).toBeLessThanOrEqual(1);
    // Status is on the card's first line, inside the screen: no sideways hunting.
    const status = card.getByText(/^(Active|Inactive)$/);
    const sb = (await status.boundingBox())!;
    expect(sb.x).toBeGreaterThanOrEqual(0);
    expect(sb.x + sb.width).toBeLessThanOrEqual(390);
    const title = (await card.getByRole("link").first().boundingBox())!;
    expect(Math.abs(sb.y - title.y)).toBeLessThan(24);
    // Fields carry their label; the row action is on the card and easy to tap.
    await expect(card.locator('td[data-label="At dealers"]')).toBeVisible();
    const edit = card.getByRole("button", { name: /^Edit / });
    const eb = (await edit.boundingBox())!;
    expect(eb.x + eb.width).toBeLessThanOrEqual(390);
    // The action closes the card: below the fields.
    expect(eb.y).toBeGreaterThan((await card.locator('td[data-label="At dealers"]').boundingBox())!.y);
    const area = await edit.evaluate((el) => { const r = el.getBoundingClientRect(), a = getComputedStyle(el, "::after"); return Math.min(Math.max(r.width, parseFloat(a.width) || 0), Math.max(r.height, parseFloat(a.height) || 0)); });
    expect(area).toBeGreaterThanOrEqual(44);
    await edit.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  });

  test("a wide table scrolls inside its card, shows an edge fade until the end, and the page does not move", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/inventory/allocation");
    const region = page.getByRole("region", { name: "Reservations, scrolls sideways" });
    await expect(region).toBeVisible();
    const { sw, cw } = await region.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
    expect(sw).toBeGreaterThan(cw);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    const fadeRight = region.locator("xpath=following-sibling::div[contains(@class,'bg-linear-to-l')]");
    await expect(fadeRight).toHaveCount(1);
    await region.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
    await expect(fadeRight).toHaveCount(0);                                                 // gone at the end
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    // Keyboard: the scroll area takes focus and the arrow keys scroll it.
    await region.evaluate((el) => { el.scrollLeft = 0; });
    await region.focus();
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => region.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  });

  test("the pinned first column stays in view while the table scrolls", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/inventory/movement");
    const region = page.getByRole("region", { name: "Stock movements, scrolls sideways" });
    const firstCell = region.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("TXN-");                                         // real rows, not loading placeholders
    const before = (await firstCell.boundingBox())!;
    await region.evaluate((el) => { el.scrollLeft = 300; });
    await expect.poll(() => region.evaluate((el) => el.scrollLeft)).toBeGreaterThan(100);
    const after = (await firstCell.boundingBox())!;
    expect(Math.abs(after.x - before.x)).toBeLessThan(2);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  });

  test("accessibility of the card table and the scrolling tables", async ({ page }) => {
    await signIn(page, RM);
    for (const [route, sel] of [["/products", "main table"], ["/inventory/allocation", "main [role=region]"], ["/inventory/movement", "main [role=region]"],
      ["/stock-requests/all", "main table"], ["/sales", "main table"], ["/resellers", "main table"], ["/replenishment", "main table"], ["/backorders", "main table"]]) {
      await page.goto(route);
      await expect(page.locator(sel).first()).toBeVisible();
      expect(await axe(page, sel), route).toEqual([]);
    }
  });
});

test.describe("tables on a tablet (touch)", () => {
  test.use(TABLET);

  test("sortable headers and checkboxes answer taps across 44px; Warehouse rows are comfortable", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    const sort = page.getByRole("columnheader", { name: /Product/ }).getByRole("button");
    const sortArea = await sort.evaluate((el) => { const r = el.getBoundingClientRect(), a = getComputedStyle(el, "::after"); return Math.min(Math.max(r.width, parseFloat(a.width) || 0), Math.max(r.height, parseFloat(a.height) || 0)); });
    expect(sortArea).toBeGreaterThanOrEqual(44);
    await sort.click();
    await expect(page.getByRole("columnheader", { name: /Product/ })).toHaveAttribute("aria-sort", "ascending");

    await page.goto("/invoices");
    const box = page.getByRole("checkbox", { name: /^Select SAL-/ }).first();
    await expect(box).toBeVisible();
    const hit = await box.evaluate((el) => { const l = el.closest("label")!, r = l.getBoundingClientRect(), a = getComputedStyle(l, "::after"); return Math.min(Math.max(r.width, parseFloat(a.width) || 0), Math.max(r.height, parseFloat(a.height) || 0)); });
    expect(hit).toBeGreaterThanOrEqual(44);
    expect(await axe(page, "main table")).toEqual([]);

    await page.goto("/warehouse");
    const row = page.getByRole("table", { name: "Warehouse stock" }).locator("tbody tr").first();
    await expect(row).toContainText("WH-");
    expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(52);
    // Comfortable density on touch: quantities are 16px / 600 for reading at arm's length.
    const qty = row.locator("td.num").first();
    expect(await qty.evaluate((el) => [getComputedStyle(el).fontSize, getComputedStyle(el).fontWeight])).toEqual(["16px", "600"]);
  });
});

test.describe("tables on a desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("dense layout is unchanged: no comfortable density with a mouse, Products stays a table", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/warehouse");
    const row = page.getByRole("table", { name: "Warehouse stock" }).locator("tbody tr").first();
    await expect(row).toContainText("WH-");                                                // real rows, not loading placeholders
    // With a mouse the comfortable density does not apply: 14px quantities, rows only as tall as their two-line tyre cell.
    expect(await row.locator("td.num").first().evaluate((el) => getComputedStyle(el).fontSize)).toBe("14px");
    expect(Math.round((await row.boundingBox())!.height)).toBeLessThanOrEqual(56);
    await page.goto("/products");
    const card = page.getByRole("table", { name: "Products" }).locator("tbody tr").first();
    await expect(card).toContainText("E2E-");
    expect(await card.evaluate((el) => getComputedStyle(el).display)).toBe("table-row");
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Phase 4C: every migrated card table, checked the same way. On a phone: rows are cards; the identifier is visible; the
// status sits on the card's first line inside the screen; the chosen fields show their labels; the row action is
// visible; the page does not scroll sideways. On a tablet: the same table is still a dense table and the page fits.

interface CardTable { route: () => string; tab?: string; table: string; status?: boolean; fields: string[]; action?: boolean; as?: "dealer" | "rep" | "wm" | "fm" }
const CARD_TABLES: CardTable[] = [
  // Group 1: inventory and stock
  { route: () => "/warehouse", table: "Warehouse stock", fields: ["Available", "Reserved", "Demand"], action: true },
  { route: () => "/consignment", table: "Consignment stock", fields: ["Available", "On hand"] },
  { route: () => "/stock-requests/all", table: "Stock requests", status: true, fields: ["Requested", "Required", "Priority"] },
  { route: () => `/stock-requests/${records.stockRequestId}`, table: "Requested tyres", fields: ["Requested", "Approved", "Shipped", "Delivered"] },
  { route: () => "/replenishment", table: "To pick", status: true, fields: ["Pick qty"] },
  { route: () => `/replenishment/${records.replenishmentId}`, table: "Allocations", status: true, fields: ["Qty", "Dispatched"] },
  { route: () => "/backorders", table: "Backorders", status: true, fields: ["Outstanding", "Urgency"] },
  { route: () => "/", table: "Stock requests", status: true, fields: ["Units", "Required"], as: "dealer" },
  // Group 2: movement and fulfilment
  { route: () => "/transfers", table: "Transfers", status: true, fields: ["Route", "Qty"] },
  { route: () => "/replenishment", tab: "Deliveries", table: "Deliveries", status: true, fields: ["Dispatched", "Received"], action: true },
  // Group 3: commercial
  { route: () => "/sales", table: "Sales", status: true, fields: ["Date", "Tyres", "Replacement"] },
  { route: () => "/invoices", table: "Sold, not invoiced", status: true, fields: ["Tyre", "Qty", "Sale date"] },
  { route: () => "/invoices", tab: "Invoice records", table: "Invoice records", status: true, fields: ["Created", "Tyres"] },
  { route: () => "/purchasing", table: "Purchase orders", status: true, fields: ["Expected", "Received / ordered"], action: true },
  { route: () => "/my-sales", table: "My sales", status: true, fields: ["Date", "Tyres", "Units"], as: "dealer" },
  // Group 4: dealer operations
  { route: () => "/sales", tab: "Stocktakes", table: "Stock checks", status: true, fields: ["Count date", "Net variance"] },
  { route: () => `/stocktakes/${records.stocktakeId}`, table: "Counted tyres", fields: ["Expected", "Counted", "Variance"] },
  { route: () => "/resellers", table: "Dealers", status: true, fields: ["Stock", "Waiting", "Sold, not invoiced"] },
  { route: () => `/resellers/${records.resellerId}`, tab: "Consignment stock", table: "Dealer stock", fields: ["On hand", "Target", "Unmet"], action: true },
  { route: () => `/resellers/${records.resellerId}`, tab: "Stocktakes", table: "Stock checks", status: true, fields: ["Count date", "Net variance"] },
  { route: () => `/resellers/${records.resellerId}`, tab: "Profile", table: "Shops", status: true, fields: [] },
  { route: () => "/", table: "My stock", fields: ["In stock", "Agreed level", "On the way"], as: "dealer" },
  { route: () => "/", table: "My dealers", status: true, fields: ["Last stock check", "Sold this month", "Waiting"], as: "rep" },
  // Group 5: administration and dashboards
  { route: () => "/admin", table: "Users", status: true, fields: ["Email"] },
  { route: () => "/admin", tab: "Pilot feedback", table: "Pilot feedback", status: true, fields: ["Page"] },
  { route: () => "/", table: "Your dealers this month", fields: ["Sold", "In stock", "Waiting"] },
  { route: () => "/", table: "Transfers", status: true, fields: ["Route", "Qty"] },
  { route: () => "/", table: "Supplier orders", status: true, fields: ["Expected", "Outstanding"], as: "wm" },
  { route: () => "/", table: "Dealers to invoice", fields: ["Tyres", "Sales", "Oldest"], as: "fm" },
  { route: () => "/", table: "Invoice records to complete", status: true, fields: ["Created", "Tyres"], as: "fm" },
  { route: () => "/", table: "Deliveries", status: true, fields: ["Dispatched", "Units"], as: "dealer" },
];

/** Tables that keep scrolling on phones because the relationship between columns matters. */
const SCROLL_TABLES: { route: string; tab?: string; region: string; pinned?: boolean }[] = [
  { route: "/inventory", region: "Stock by tyre", pinned: true },
  { route: "/inventory/movement", region: "Stock movements", pinned: true },
  { route: "/inventory/allocation", region: "Reservations" },
  { route: "/admin", tab: "Audit log", region: "Change history", pinned: true },
];

test.describe("scrolling tables on a phone", () => {
  test.use(PHONE);
  test("scroll stays inside the table; pinned columns stay put; the page fits", async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page, RM);
    const problems: string[] = [];
    for (const t of SCROLL_TABLES) {
      await page.goto(t.route);
      await page.waitForLoadState("networkidle");
      if (t.tab) await page.getByRole("tab", { name: t.tab }).click();
      const region = page.getByRole("region", { name: `${t.region}, scrolls sideways` });
      await region.waitFor({ timeout: 5000 }).catch(() => {});
      if (!(await region.isVisible())) { problems.push(`${t.route}: no scroll region "${t.region}"`); continue; }
      await expect(region.locator("tbody tr").first().locator(".animate-shimmer")).toHaveCount(0);
      if (t.pinned) {
        const cell = region.locator("tbody tr").first().locator("td").first();
        const before = (await cell.boundingBox())!;
        await region.evaluate((el) => { el.scrollLeft = 300; });
        await page.waitForTimeout(100);
        const after = (await cell.boundingBox())!;
        if (Math.abs(after.x - before.x) > 2) problems.push(`${t.route}: pinned column moved ${after.x - before.x}px`);
      }
      const w = await pageWidth(page);
      if (w > 390) problems.push(`${t.route}: page ${w}px wide`);
    }
    expect(problems).toEqual([]);
  });
});

async function cardRow(page: Page, table: string) {
  const t = page.getByRole("table", { name: table }).first();
  await expect(t).toBeVisible();
  const row = t.locator("tbody tr").first();
  await expect(row).toBeVisible();
  await expect(row.locator(".animate-shimmer")).toHaveCount(0);                            // real rows, not loading placeholders
  return row;
}

test.describe("migrated card tables on a phone", () => {
  test.use(PHONE);
  test("identifier, status, key fields and action are on the card; nothing scrolls sideways", async ({ page }) => {
    test.setTimeout(240_000);
    const problems: string[] = [];
    let who = "";
    for (const c of CARD_TABLES) {
      const user = c.as ? { dealer: records.dealer, rep: SR, wm: WM, fm: records.finance }[c.as] : RM;
      if (user !== who) { await page.context().clearCookies(); await signIn(page, user); who = user; }
      await page.goto(c.route());
      await page.waitForLoadState("networkidle");
      if (c.tab) await page.getByRole("tab", { name: c.tab }).click();
      const row = await cardRow(page, c.table);
      const where = `${c.route()} "${c.table}"`;
      const info = await row.evaluate((tr) => {
        const cells = [...tr.children] as HTMLElement[];
        const shown = cells.filter((td) => getComputedStyle(td).display !== "none");
        const firstLine = shown.filter((td) => getComputedStyle(td).gridRowStart === "1");
        const box = (el: HTMLElement) => { const r = el.getBoundingClientRect(); return { l: r.left, r: r.right, w: r.width }; };
        return { display: getComputedStyle(tr).display, firstLine: firstLine.map(box), shown: shown.length, cells: cells.length };
      });
      if (info.display !== "grid") problems.push(`${where}: not a card (${info.display})`);
      if (info.firstLine.length < (c.status ? 2 : 1)) problems.push(`${where}: identifier/status not on the first line`);
      for (const b of info.firstLine) if (b.l < 0 || b.r > 391 || b.w === 0) problems.push(`${where}: first line outside the screen`);
      if (info.shown > 6) problems.push(`${where}: ${info.shown} cells on the card (keep it to identifier, status, 2–4 fields, action)`);
      for (const f of c.fields) if (!(await row.locator(`td[data-label="${f}"]`).first().isVisible())) problems.push(`${where}: field "${f}" not visible`);
      if (c.action) {
        const act = row.locator("td").last().locator("button, a").first();
        if (!(await act.isVisible())) problems.push(`${where}: row action not visible`);
        else { const b = (await act.boundingBox())!; if (b.x < 0 || b.x + b.width > 391) problems.push(`${where}: row action outside the screen`); }
      }
      const w = await pageWidth(page);
      if (w > 390) problems.push(`${where}: page ${w}px wide`);
    }
    expect(problems).toEqual([]);
  });
});

test.describe("migrated card tables on a tablet stay tables", () => {
  test.use(TABLET);
  test("dense table layout and no sideways page scrolling at 820px", async ({ page }) => {
    test.setTimeout(240_000);
    const problems: string[] = [];
    let who = "";
    for (const c of CARD_TABLES) {
      const user = c.as ? { dealer: records.dealer, rep: SR, wm: WM, fm: records.finance }[c.as] : RM;
      if (user !== who) { await page.context().clearCookies(); await signIn(page, user); who = user; }
      await page.goto(c.route());
      await page.waitForLoadState("networkidle");
      if (c.tab) await page.getByRole("tab", { name: c.tab }).click();
      const row = await cardRow(page, c.table);
      const display = await row.evaluate((tr) => getComputedStyle(tr).display);
      if (display !== "table-row") problems.push(`${c.route()} "${c.table}": ${display}`);
      const w = await pageWidth(page);
      if (w > 820) problems.push(`${c.route()}: page ${w}px wide`);
    }
    expect(problems).toEqual([]);
  });
});

test.describe("Products on a tablet in portrait", () => {
  test.use(TABLET);
  test("Status is in view without scrolling the table", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    const status = page.getByRole("table", { name: "Products" }).getByRole("columnheader", { name: "Status" });
    await expect(status).toBeVisible();
    const b = (await status.boundingBox())!;
    expect(b.x + b.width).toBeLessThanOrEqual(820);
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Phase 4D: workflow actions on phones. One primary action docked at the bottom (MobileActionBar), secondary header
// actions in a "More" menu, notifications above the bar, dialogs keep their own footer.

const bar = (page: Page) => page.locator("[data-mobile-action-bar]:visible");
const boxOf = async (page: Page, l: ReturnType<Page["locator"]>) => (await l.boundingBox())!;
const overlaps = (a: { x: number; y: number; width: number; height: number }, b: typeof a) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** Workflows whose primary action docks at the bottom of a phone. */
const STICKY: { name: string; route: () => string | Promise<string>; action: string; before?: (page: Page) => Promise<void> }[] = [
  { name: "New stock request", route: () => "/stock-requests/new", action: "Submit for approval" },
  { name: "Stock request detail", route: () => `/stock-requests/${records.stockRequestId}`, action: "Approve…" },
  { name: "Replenishment detail", route: () => `/replenishment/${records.pickReplenishmentId}`, action: "Ship" },
  { name: "New transfer", route: () => "/transfers/new", action: "Check availability" },
  { name: "Transfer detail", route: () => `/transfers/${records.transferId}`, action: "Approve & choose source" },
  { name: "Invoice selection", route: () => "/invoices", action: "Create invoice record (1 line)",
    before: async (page) => {
      const box = page.getByRole("checkbox", { name: /^Select SAL-/ }).first();
      await box.locator("xpath=ancestor::label").tap();                         // the 44px tap area around the box
      await expect(box).toBeChecked();
    } },
  { name: "Mark as invoiced in Xero", route: () => `/invoices/${records.invoiceId}`, action: "Mark as invoiced in Xero" },
  { name: "Stock check count", route: () => "/stocktakes/new", action: "Submit count" },
  { name: "Stock check detail", action: "Submit count", route: async () => {
    // A counted but not yet submitted stock check (the shared one is already complete).
    const f = await setup({ resellerStock: 2, warehouseStock: 0, tag: "RSD" });
    const rm = await apiAs(RM);
    const st = await json<{ id: number }>(await rm.post("/api/stocktakes", { data: { location_id: f.locationId, count_date: today(),
      counts: [{ product_id: f.productId, counted_qty: 2 }] } }));
    await rm.dispose();
    return `/stocktakes/${st.id}`;
  } },
];

test.describe("workflow actions on a phone", () => {
  test.use(PHONE);

  test("the primary action is docked at the bottom, shown once, above the safe area; the page fits", async ({ page }) => {
    test.setTimeout(180_000);
    // Pop-up notifications from other tests' activity would sit over the bottom of the page; they are tested below.
    await page.route("**/api/notifications**", (r) => r.fulfill({ status: 200, contentType: "application/json",
      body: r.request().url().includes("unread-count") ? '{"unread":0,"latest_id":0}' : "[]" }));
    await signIn(page, RM);
    for (const w of STICKY) {
      await page.goto(await w.route());
      // Wait for the page itself, not network idle: polling and link prefetches can keep the network busy under load.
      await page.locator("main h1").first().waitFor();
      await w.before?.(page);
      const b = bar(page);
      await expect(b, w.name).toHaveCount(1);
      const btn = b.getByRole("button", { name: w.action, exact: true });
      await expect(btn, w.name).toBeVisible();
      // Shown once: no second visible copy of the same action anywhere on the page.
      await expect(page.getByRole("button", { name: w.action, exact: true }), w.name).toHaveCount(1);
      const bb = await boxOf(page, b);
      expect(Math.round(bb.y + bb.height), w.name).toBe(844);                    // flush with the bottom of the screen
      const btnBox = await boxOf(page, btn);
      expect(btnBox.height, w.name).toBeGreaterThanOrEqual(44);
      // Safe area: the bar's bottom padding is max(12px, the iPhone home-indicator inset).
      const pad = await b.evaluate((el) => getComputedStyle(el).paddingBottom);
      expect(parseFloat(pad), w.name).toBeGreaterThanOrEqual(12);
      expect(await pageWidth(page), w.name).toBeLessThanOrEqual(390);
      if (["New stock request", "Mark as invoiced in Xero", "Stock check count", "Invoice selection"].includes(w.name)) {
        expect(await axe(page, "main"), w.name).toEqual([]);
      }
    }
  });

  test("the bar's height is reserved at the end of the page, so the last field is never covered", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/stock-requests/new");
    await page.waitForLoadState("networkidle");
    const b = bar(page);
    const h = (await boxOf(page, b)).height;
    // The bar publishes its height; the page's bottom padding and scroll padding grow by it.
    const vars = await page.evaluate(() => ({
      bar: getComputedStyle(document.documentElement).getPropertyValue("--action-bar-height"),
      pad: parseFloat(getComputedStyle(document.querySelector("main")!).paddingBottom),
      safe: [...document.styleSheets].some((s) => { try { return [...s.cssRules].some((r) => r.cssText.includes("safe-area-inset-bottom")); } catch { return false; } }),
    }));
    expect(parseFloat(vars.bar)).toBeCloseTo(h, 0);
    expect(vars.pad).toBeGreaterThanOrEqual(h + 24 - 1);
    expect(vars.safe).toBe(true);
    // Scrolled to the end, the last field sits above the bar.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const notes = page.getByLabel("Notes for the Central Team");
    expect((await boxOf(page, notes)).y + (await boxOf(page, notes)).height).toBeLessThanOrEqual((await boxOf(page, b)).y);
    // The bar comes after the last field in the document, so the focus order is the form, then its actions.
    expect(await notes.evaluate((n, bar) => !!(n.compareDocumentPosition(bar!) & Node.DOCUMENT_POSITION_FOLLOWING),
      await b.elementHandle())).toBe(true);
  });

  test("the docked primary action is reached by keyboard after the page content", async ({ page }) => {
    await signIn(page, RM);
    await page.goto(`/transfers/${records.transferId}`);
    await page.waitForLoadState("networkidle");
    const primary = bar(page).getByRole("button", { name: "Approve & choose source" });
    let previous = "";
    for (let i = 0; i < 80 && !(await primary.evaluate((el) => el === document.activeElement)); i++) {
      previous = await page.evaluate(() => document.activeElement?.closest("main") ? "main" : document.activeElement?.closest("header") ? "header" : "other");
      await page.keyboard.press("Tab");
    }
    await expect(primary).toBeFocused();
    expect(previous).toBe("main");                                              // reached from the page content, not the header
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Approve transfer" })).toBeVisible();
    await page.keyboard.press("Escape");
  });

  test("while a text field is focused (keyboard open) the bar steps out of the way instead of covering it", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/stock-requests/new");
    await page.waitForLoadState("networkidle");
    const notes = page.getByLabel("Notes for the Central Team");
    await notes.tap();
    await notes.fill("Please deliver on Monday");
    const b = page.locator("[data-mobile-action-bar]");
    expect(await b.evaluate((el) => getComputedStyle(el).position)).not.toBe("fixed");
    const n = await boxOf(page, notes);
    const viewport = await page.evaluate(() => window.visualViewport?.height ?? window.innerHeight);
    expect(n.y + n.height).toBeLessThanOrEqual(viewport);
    // Leaving the field brings the bar back.
    await page.getByRole("heading", { level: 1 }).click();
    await expect.poll(() => b.evaluate((el) => getComputedStyle(el).position)).toBe("fixed");
  });

  test("secondary header actions move into More; the menu works with keyboard and touch; destructive items are explicit", async ({ page }) => {
    test.setTimeout(90_000);
    const f = await setup({ resellerStock: 0, target: 4, warehouseStock: 4, tag: "RMM" });
    const rm = await apiAs(RM);
    const sr = await json<{ id: number; number: string }>(await rm.post("/api/stock-requests", { data: {
      location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 1 }] } }));
    await rm.dispose();
    await signIn(page, RM);
    await page.goto(`/stock-requests/${sr.id}`);
    await page.waitForLoadState("networkidle");
    // Desktop header buttons are not shown on the phone; the next step is in the bar, the rest behind More.
    await expect(page.getByRole("button", { name: "Start review" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Print pick sheet" })).toHaveCount(0);
    await expect(bar(page).getByRole("button", { name: "Approve…" })).toBeVisible();
    const more = page.getByRole("button", { name: "More actions" });
    await expect(more).toBeVisible();
    expect((await boxOf(page, more)).height).toBeGreaterThanOrEqual(44);
    // Keyboard: Enter opens and focuses the first item, arrows move, Escape closes and returns focus.
    await more.focus();
    await page.keyboard.press("Enter");
    const menu = page.getByRole("menu", { name: "More actions" });
    await expect(menu).toBeVisible();
    const items = menu.getByRole("menuitem");
    await expect(items.first()).toBeFocused();
    expect(await items.allTextContents()).toEqual(["Print pick sheet", "Start review", "Reject request", "Cancel request"]);
    for (const item of await items.all()) expect((await boxOf(page, item)).height).toBeGreaterThanOrEqual(44);
    const m = await boxOf(page, menu);                                           // the whole menu is on screen
    expect(m.x).toBeGreaterThanOrEqual(0);
    expect(m.x + m.width).toBeLessThanOrEqual(390);
    await page.keyboard.press("ArrowDown");
    await expect(items.nth(1)).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(more).toBeFocused();
    expect(await axe(page, "main")).toEqual([]);
    // Destructive items come last, in the danger colour, and say exactly what they do.
    await more.tap();
    const danger = await items.evaluateAll((els) => els.map((e) => ({ text: e.textContent, color: getComputedStyle(e).color })));
    const red = danger.find((d) => d.text === "Reject request")!.color;
    expect(danger.slice(2).every((d) => d.color === red)).toBe(true);
    expect(danger.slice(0, 2).every((d) => d.color !== red)).toBe(true);
    expect(await axe(page, "main")).toEqual([]);
    // A menu action works: Start review moves the request on.
    await menu.getByRole("menuitem", { name: "Start review" }).tap();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Under review");
  });

  test("a dialog keeps its own footer in view and never gets the page's bar", async ({ page }) => {
    await signIn(page, RM);
    await page.goto(`/transfers/${records.transferId}`);
    await page.waitForLoadState("networkidle");
    await bar(page).getByRole("button", { name: "Approve & choose source" }).tap();
    const dialog = page.getByRole("dialog", { name: "Approve transfer" });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("[data-mobile-action-bar]")).toHaveCount(0);
    // The page bar is under the dialog's backdrop: the bottom of the screen belongs to the dialog.
    const hit = await page.evaluate(() => document.elementFromPoint(195, 838)?.closest("[data-mobile-action-bar]") !== null);
    expect(hit).toBe(false);
    await expect(dialog.getByRole("button", { name: "Back" })).toBeInViewport();
    await dialog.getByRole("button", { name: "Back" }).tap();
    // A long dialog (New dealer): its Create button stays at the bottom of the screen without scrolling.
    await page.goto("/resellers");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "New dealer" }).first().tap();
    const create = page.getByRole("dialog", { name: "New dealer" }).getByRole("button", { name: "Create dealer" });
    await expect(create).toBeInViewport();
    expect((await boxOf(page, create)).y + (await boxOf(page, create)).height).toBeLessThanOrEqual(844);
  });

  test("a new notification sits above the bar and never covers the primary action", async ({ page }) => {
    test.setTimeout(90_000);
    const f = await setup({ resellerStock: 0, warehouseStock: 4, tag: "RNB" });
    await signIn(page, RM);
    await page.goto("/stock-requests/new");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);   // the first poll has set the baseline
    for (const d of await page.getByRole("button", { name: "Dismiss notification" }).all()) await d.click().catch(() => {});
    const number = await dealerSubmitsRequest(f);
    const toast = page.getByRole("status", { name: "New notifications" }).locator("> div", { hasText: number });
    await expect(toast).toBeVisible({ timeout: 25_000 });
    const t = await boxOf(page, toast);
    const b = await boxOf(page, bar(page));
    const primary = await boxOf(page, bar(page).getByRole("button", { name: "Submit for approval" }));
    expect(t.y + t.height).toBeLessThanOrEqual(b.y);
    expect(t.y + t.height).toBeGreaterThan(b.y - 140);                          // still docked at the bottom
    expect(overlaps(t, primary)).toBe(false);
  });
});

/** A dealer submits a stock request, which notifies the Relationship Manager. Returns its number. */
async function dealerSubmitsRequest(f: { resellerId: number; locationId: number; productId: number }) {
  const rm = await apiAs(RM);
  const email = `rsp-dealer-${Date.now().toString(36)}@e2e.example.com`;
  await json(await rm.post("/api/users", { data: { email, full_name: "E2E Dealer", password: "temporary-pass-1", role: "RESELLER", reseller_id: f.resellerId } }));
  await rm.dispose();
  const dealer = await apiAs(email, "temporary-pass-1");
  const sr = await json<{ number: string }>(await dealer.post("/api/stock-requests", { data: {
    location_id: f.locationId, submit: true, lines: [{ product_id: f.productId, quantity: 1 }] } }));
  await dealer.dispose();
  return sr.number;
}

test.describe("workflow actions on a tablet in portrait", () => {
  test.use(TABLET);

  test("a notification docks at the bottom, clear of the header buttons", async ({ page }) => {
    test.setTimeout(90_000);
    const f = await setup({ resellerStock: 0, warehouseStock: 4, tag: "RNTB" });
    await signIn(page, RM);
    await page.goto("/products");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    for (const d of await page.getByRole("button", { name: "Dismiss notification" }).all()) await d.click().catch(() => {});
    const number = await dealerSubmitsRequest(f);
    const toast = page.getByRole("status", { name: "New notifications" }).locator("> div", { hasText: number });
    await expect(toast).toBeVisible({ timeout: 25_000 });
    const t = await boxOf(page, toast);
    expect(t.y + t.height).toBeGreaterThan(1180 - 140);
    for (const name of ["More actions", "Add product"]) {
      expect(overlaps(t, await boxOf(page, page.getByRole("button", { name })))).toBe(false);
    }
  });
});

test.describe("workflow actions on a desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("header actions are unchanged: no bar, no More menu, the primary action in the header or in place", async ({ page }) => {
    await signIn(page, RM);
    await page.goto(`/stock-requests/${records.stockRequestId}`);
    await page.waitForLoadState("networkidle");
    await expect(bar(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "More actions" })).toHaveCount(0);
    for (const name of ["Start review", "Reject", "Approve…", "Cancel request"]) {
      const b = page.getByRole("button", { name, exact: true });
      await expect(b).toHaveCount(1);
      expect((await boxOf(page, b)).y).toBeLessThan(300);                       // in the page header
    }
    await expect(page.getByRole("link", { name: "Print pick sheet" })).toBeVisible();
    // A form keeps its buttons in place, and nothing reserves room for a bar.
    await page.goto("/stock-requests/new");
    await page.waitForLoadState("networkidle");
    const inPlace = page.locator("[data-mobile-action-bar]");
    expect(await inPlace.evaluate((el) => getComputedStyle(el).position)).toBe("static");
    await expect(page.getByRole("button", { name: "Submit for approval" })).toBeVisible();
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--action-bar-height").trim())).toBe("0px");
    await page.goto("/products");
    for (const name of ["Import from Excel", "Add product"]) await expect(page.getByRole("button", { name })).toBeVisible();
    await expect(page.getByRole("link", { name: /Excel template/ })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Phase 4E: phone filters and sorting (one sheet), quick filters in one scrolling row, the tablet-landscape icon rail.

test.describe("filters and sorting on a phone", () => {
  test.use(PHONE);

  test("Filters opens a sheet with visible labels; focus stays inside; Escape returns focus to Filters", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    await page.waitForLoadState("networkidle");
    // Search stays in view; the secondary filters are behind the Filters button.
    await expect(page.getByRole("searchbox", { name: "Search table" })).toBeVisible();
    await expect(page.getByLabel("Brand filter")).toHaveCount(0);
    const button = page.getByRole("button", { name: /^Filters/ });
    await expect(button).toHaveText("Filters");
    expect((await boxOf(page, button)).height).toBeGreaterThanOrEqual(44);
    await button.tap();
    const sheet = page.getByRole("dialog", { name: "Filters and sort" });
    await expect(sheet).toBeVisible();
    for (const label of ["Brand", "Size", "Availability", "Status", "Sort by", "Order"]) await expect(sheet.getByText(label, { exact: true }).first()).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Clear all" })).toBeVisible();
    await expect(sheet.getByRole("button", { name: /^Apply/ })).toBeVisible();
    // Focus is trapped: tabbing many times never leaves the sheet.
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press("Tab");
      expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    }
    expect(await axe(page, "[role=dialog]")).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(button).toBeFocused();
  });

  test("the active filter count is shown, Clear all resets it, and the size field is usable", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    await page.waitForLoadState("networkidle");
    const button = page.getByRole("button", { name: /^Filters/ });
    await button.tap();
    const sheet = page.getByRole("dialog", { name: "Filters and sort" });
    // The size field is full width: its placeholder is not cut off.
    const size = sheet.getByLabel("Size filter");
    const fits = await size.evaluate((el: HTMLInputElement) => {
      const cs = getComputedStyle(el), ctx = document.createElement("canvas").getContext("2d")!;
      ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      return ctx.measureText(el.placeholder).width <= el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    });
    expect(fits).toBe(true);
    expect((await boxOf(page, size)).width).toBeGreaterThan(300);
    await size.fill("205");
    await sheet.getByLabel("Status filter").selectOption("false");
    await sheet.getByRole("button", { name: /^Apply/ }).tap();
    await expect(sheet).toBeHidden();
    await expect(button).toHaveText("Filters (2)");
    await button.tap();
    await expect(sheet.getByLabel("Size filter")).toHaveValue("205");                 // the filter keeps its value
    await sheet.getByRole("button", { name: "Clear all" }).tap();
    await expect(sheet.getByLabel("Size filter")).toHaveValue("");
    await expect(sheet.getByLabel("Status filter")).toHaveValue("true");               // back to the default (Active)
    await sheet.getByRole("button", { name: /^Apply/ }).tap();
    await expect(button).toHaveText("Filters");
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  });

  test("sorting a card table: Sort by and order, announced, and the same sort as the desktop headers", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/products");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: /^Filters/ }).tap();
    const sheet = page.getByRole("dialog", { name: "Filters and sort" });
    const sortBy = sheet.getByRole("group", { name: "Sort by" });
    // Only the useful fields are offered.
    expect(await sortBy.getByRole("radio").evaluateAll((els) => els.map((e) => e.parentElement!.textContent))).toEqual(
      ["Default order", "Name", "Size", "Warehouse stock", "Backorder"]);
    await expect(sheet.getByRole("radio", { name: "Descending" })).toBeDisabled();  // nothing to order until a field is chosen
    await sortBy.getByRole("radio", { name: "Name" }).check();
    await sheet.getByRole("radio", { name: "Descending" }).check();
    await sheet.getByRole("button", { name: /^Apply/ }).tap();
    const status = page.getByText("Sorted by Name, descending");
    await expect(status).toBeVisible();
    expect(await status.getAttribute("aria-live")).toBe("polite");
    const names = await page.getByRole("table", { name: "Products" }).locator("tbody tr td:first-child a").allTextContents();
    expect(names.length).toBeGreaterThan(1);
    expect(names).toEqual([...names].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0)));
    // Screen readers get the same state from the (hidden) column header.
    await expect(page.getByRole("columnheader", { name: /Product/ })).toHaveAttribute("aria-sort", "descending");
  });

  test("quick filters stay one row that scrolls inside itself; the page does not move; focus stays visible", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/warehouse");
    await page.waitForLoadState("networkidle");
    const row = page.getByRole("group", { name: "Quick filters" });
    const chips = row.getByRole("button");
    const tops = await chips.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
    expect(new Set(tops).size).toBe(1);                                          // one row, never wrapped
    expect(await row.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    for (const chip of await chips.all()) expect((await boxOf(page, chip)).height).toBeGreaterThanOrEqual(44);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    // Keyboard: the last chip scrolls into view when focused.
    await chips.last().focus();
    const r = await boxOf(page, row), c = await boxOf(page, chips.last());
    expect(c.x + c.width).toBeLessThanOrEqual(r.x + r.width + 1);
    await chips.last().tap();
    await expect(chips.last()).toHaveAttribute("aria-pressed", "true");
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  });
});

test.describe("navigation in tablet landscape (1180px)", () => {
  test.use({ viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true });

  test("an icon rail with named icons; it expands and collapses by keyboard and touch; the current page is clear", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/warehouse");
    await page.waitForLoadState("networkidle");
    const rail = page.getByRole("complementary", { name: "Navigation" });
    expect(Math.round((await boxOf(page, rail)).width)).toBe(64);
    await expect(page.getByRole("button", { name: "Open menu" })).toBeHidden();
    const links = rail.getByRole("navigation", { name: "Main" }).getByRole("link");
    expect(await links.count()).toBeGreaterThan(8);
    for (const l of await links.all()) {
      expect((await l.innerText()).trim().length > 0 || (await l.getAttribute("title"))).toBeTruthy();
      expect((await boxOf(page, l)).height).toBeGreaterThanOrEqual(44);
    }
    const current = rail.locator("a[aria-current=page]");
    await expect(current).toHaveAccessibleName("Warehouse");
    expect(await current.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    await expect(current.locator(".bg-brand")).toBeVisible();                   // the yellow marker
    expect(await axe(page, "aside")).toEqual([]);
    // Expand by keyboard, collapse with Escape (focus back on the button).
    const toggle = rail.getByRole("button", { name: "Expand navigation" });
    expect((await boxOf(page, toggle)).height).toBeGreaterThanOrEqual(44);
    await toggle.focus();
    await page.keyboard.press("Enter");
    const collapse = rail.getByRole("button", { name: "Collapse navigation" });
    await expect(collapse).toHaveAttribute("aria-expanded", "true");
    expect(Math.round((await boxOf(page, rail)).width)).toBe(256);
    await expect(rail.getByText("Warehouse", { exact: true }).first()).toBeVisible();
    expect(await axe(page, "aside")).toEqual([]);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Escape");
    await expect(rail.getByRole("button", { name: "Expand navigation" })).toBeFocused();
    expect(Math.round((await boxOf(page, rail)).width)).toBe(64);
    // Touch: expand, then choose a page; the rail collapses on navigation.
    await rail.getByRole("button", { name: "Expand navigation" }).tap();
    await rail.getByRole("link", { name: "Products" }).tap();
    await page.waitForURL("**/products");
    expect(Math.round((await boxOf(page, rail)).width)).toBe(64);
    await expect(rail.locator("a[aria-current=page]")).toHaveAccessibleName("Products");
  });

  test("tables get the width back: the page content is 192px wider than with the full sidebar", async ({ page }) => {
    await signIn(page, RM);
    await page.goto("/warehouse");
    await page.waitForLoadState("networkidle");
    const main = await boxOf(page, page.locator("main"));
    expect(Math.round(main.width)).toBe(1180 - 64);
    expect(await pageWidth(page)).toBeLessThanOrEqual(1180);
  });

  test("stock request detail: the header actions sit on one line beside the title", async ({ page }) => {
    await signIn(page, RM);
    await page.goto(`/stock-requests/${records.stockRequestId}`);
    await page.waitForLoadState("networkidle");
    const tops = [];
    for (const name of ["Start review", "Reject", "Approve…", "Cancel request"]) tops.push(Math.round((await boxOf(page, page.getByRole("button", { name, exact: true }))).y));
    tops.push(Math.round((await boxOf(page, page.getByRole("link", { name: "Print pick sheet" }))).y));
    expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(4);
    await expect(bar(page)).toHaveCount(0);                                     // landscape keeps the header actions
  });
});

test.describe("navigation and filters on other sizes", () => {
  test("desktop keeps the full sidebar and inline filters; portrait tablet keeps the menu button", async ({ browser }) => {
    const desk = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await signIn(desk, RM);
    await desk.goto("/products");
    await desk.waitForLoadState("networkidle");
    expect(Math.round((await boxOf(desk, desk.getByRole("complementary", { name: "Navigation" }))).width)).toBe(256);
    await expect(desk.getByRole("button", { name: /navigation/ })).toBeHidden();
    await expect(desk.getByLabel("Brand filter")).toBeVisible();
    await expect(desk.getByRole("button", { name: /^Filters/ })).toHaveCount(0);
    await desk.close();
    const tab = await browser.newPage({ viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true });
    await signIn(tab, RM);
    await expect(tab.getByRole("button", { name: "Open menu" })).toBeVisible();
    await expect(tab.getByRole("complementary", { name: "Navigation" })).toBeHidden();
    await tab.close();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Phase 5: the login page at four widths, keyboard-only sign-in, field errors, the password toggle.

test.describe("login page", () => {
  for (const device of DEVICES) {
    test(`${device.name}: fits, the sign-in form leads, the loop is a named closed cycle, no axe issues`, async ({ browser }) => {
      const page = await browser.newPage({ viewport: { width: device.width, height: device.height }, isMobile: device.touch, hasTouch: device.touch });
      await page.goto("/login");
      const signIn = page.getByRole("button", { name: "Sign in" });
      await expect(signIn).toBeVisible();
      expect(await pageWidth(page)).toBeLessThanOrEqual(device.width);
      // The headline, unchanged, on three lines.
      const h1 = page.getByRole("heading", { level: 1 });
      await expect(h1).toHaveText("Smarter consignment.Better stock control.Faster replenishment.");
      expect(await h1.locator("span").count()).toBe(3);
      await expect(page.getByText("One view of stock across your warehouse and dealer network. Manage consignment, replenishment, transfers and backorders together.")).toBeVisible();
      // The form is in the first screen, and the button is the widest control.
      const b = await boxOf(page, signIn);
      expect(b.y + b.height).toBeLessThanOrEqual(device.height);
      expect(b.width).toBeGreaterThanOrEqual(Math.min(300, device.width - 64));
      expect(await signIn.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(28, 28, 30)");   // charcoal
      // The loop: four steps in order, Replenishment marked in yellow, ending back at the warehouse.
      const loop = page.getByRole("list", { name: /keeps stock moving/ });
      const steps = loop.getByRole("listitem");
      await expect(steps).toHaveCount(4);
      expect((await steps.allInnerTexts()).map((t) => t.split("\n")[0])).toEqual(["Warehouse", "Dealer", "Sale", "Replenishment"]);
      await expect(steps.nth(3)).toContainText("then back to the warehouse");
      expect(await steps.nth(3).locator("span").first().evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(255, 212, 0)");
      expect(await steps.nth(0).locator("span").first().evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe("rgb(255, 212, 0)");
      await expect(page.getByText("Back to the warehouse", { exact: true })).toBeVisible();
      // Phones and portrait tablets: the form before the loop. Landscape and desktop: the loop on the left, the form on the right.
      const form = await boxOf(page, page.locator("form"));
      const l = await boxOf(page, loop.locator(".."));
      if (device.width < 1024) expect(form.y).toBeLessThan(l.y);
      else expect(l.x + l.width).toBeLessThan(form.x);
      // The password toggle answers taps across 44px on touch screens.
      if (device.touch) {
        const t = await tapArea(page, "button[aria-label='Show password']");
        expect(Math.min(t.w, t.h)).toBeGreaterThanOrEqual(44);
      }
      expect(await axe(page, "body")).toEqual([]);
      await page.close();
    });
  }

  test("keyboard only: Tab through email, password and the toggle, Enter signs in", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in" }).waitFor();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Email", { exact: true })).toBeFocused();
    await page.keyboard.type(RM);
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
    await page.keyboard.type(PASSWORD);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Show password" })).toBeFocused();
    expect(await page.getByRole("button", { name: "Show password" }).evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeFocused();
    await page.keyboard.press("Enter");
    await page.waitForURL((url) => url.pathname === "/");
  });

  test("errors are linked to their fields; the password toggle keeps its name and reports its state", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in" }).click();
    const email = page.getByLabel("Email", { exact: true });
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await expect(email).toHaveAccessibleDescription("Enter the email address you use for work.");
    await expect(page.getByLabel("Password", { exact: true })).toHaveAccessibleDescription("Enter your password.");
    const toggle = page.getByRole("button", { name: "Show password" });
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await toggle.click();
    await expect(page.getByRole("button", { name: "Show password" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
    // A wrong password: the message appears above the form and is announced.
    await email.fill("nobody@e2e.example.com");
    await page.getByLabel("Password", { exact: true }).fill("wrong-password-1");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert").filter({ hasText: /Invalid email or password/ })).toBeVisible();
  });
});
