import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

/*
 * End-to-end tests CREATE DATA. Run them only against a disposable local database prepared with
 *   PILOT_FORCE_PASSWORD_CHANGE=false PILOT_RM_EMAIL=rm@e2e.example.com PILOT_WM_EMAIL=wm@e2e.example.com \
 *   PILOT_SR_EMAIL=sr@e2e.example.com PILOT_RM_PASSWORD=e2e-password-123 PILOT_WM_PASSWORD=e2e-password-123 \
 *   PILOT_SR_PASSWORD=e2e-password-123 PILOT_ADMIN_EMAIL=admin@e2e.example.com PILOT_ADMIN_PASSWORD=e2e-password-123 \
 *   python -m scripts.reset_to_pilot --confirm RESET-PILOT
 * Never point E2E_BASE_URL at the pilot or production environment.
 */
export const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password-123";
export const RM = process.env.E2E_RM_EMAIL ?? "rm@e2e.example.com";
export const WM = process.env.E2E_WM_EMAIL ?? "wm@e2e.example.com";
export const SR = process.env.E2E_SR_EMAIL ?? "sr@e2e.example.com";
export const ADMIN = process.env.E2E_ADMIN_EMAIL ?? "admin@e2e.example.com";
export const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
export const today = () => new Date().toISOString().slice(0, 10);

export async function apiAs(email: string, password = PASSWORD): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: BASE });
  const res = await ctx.post("/api/auth/login", { data: { email, password } });
  expect(res.ok(), `login ${email}`).toBeTruthy();
  return ctx;
}

export async function json<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(res.ok(), `${res.url()} → ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

export async function login(page: Page, email: string, password = PASSWORD) {
  // Leave the current page first: its background requests (data reloads, the notification poll) would get a 401
  // once the cookies are cleared, and the app's redirect to /login would abort the page.goto below.
  await page.goto("about:blank");
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

export interface Fixture {
  sku: string;
  productId: number;
  resellerId: number;
  locationId: number;
  locationCode: string;
  warehouseId: number;
}

/** The details every new dealer needs (finding 9), with the first active Sales Representative as their rep. */
export async function dealerDetails(api: APIRequestContext, run: string) {
  const reps = await json<{ id: number }[]>(await api.get("/api/staff?role=SALES_REP"));
  return { contact_name: `Contact ${run}`, email: `dealer-${run.toLowerCase()}@e2e.example.com`, phone: "09 555 0100",
    billing_address: "1 Test Street, Auckland", sales_rep_user_id: reps[0].id };
}

/** Create an isolated product + reseller (+ optional target and stock) through the API. */
export async function setup(opts: { resellerStock: number; target?: number; warehouseStock: number; tag: string }): Promise<Fixture> {
  const mgr = await apiAs(RM);   // Relationship Manager: resellers and targets
  const wh = await apiAs(WM);    // Warehouse Manager: product master and stock
  const run = `${opts.tag}${Date.now().toString(36).toUpperCase()}`;
  const product = await json<{ id: number; sku: string }>(await wh.post("/api/products", { data: {
    sku: `E2E-${run}`, brand: "E2E", pattern: `Pattern ${run}`, width: 205, aspect_ratio: 55, rim_diameter: "16",
    load_index: "91", speed_rating: "V", list_price: "150.00", cost_price: "100.00" } }));
  const reseller = await json<{ id: number; locations: { id: number; code: string }[] }>(await mgr.post("/api/resellers", { data: {
    ...(await dealerDetails(mgr, run)), account_ref: `E${run}`, business_name: `E2E Reseller ${run}`,
    agreement: { reference: `AGR-${run}`, transfer_consent: "PRE_AUTHORISED" },
    locations: [{ code: `E${run}-MAIN`, name: `E2E ${run} Main`, address_line1: "1 Test Street", city: "Auckland" }] } }));
  const loc = reseller.locations[0];
  const warehouses = await json<{ id: number; is_default_warehouse: boolean }[]>(await wh.get("/api/locations?type=WAREHOUSE"));
  const whLoc = warehouses.find((w) => w.is_default_warehouse) ?? warehouses[0];
  if (opts.target !== undefined) {
    await json(await mgr.put("/api/allocations", { data: { location_id: loc.id, product_id: product.id, target_qty: opts.target, reason: "E2E setup" } }));
  }
  if (opts.resellerStock) {
    await json(await wh.post("/api/inventory/opening-balances", { data: { location_id: loc.id, lines: [{ product_id: product.id, quantity: opts.resellerStock }] } }));
  }
  if (opts.warehouseStock) {
    await json(await wh.post("/api/inventory/opening-balances", { data: { location_id: whLoc.id, lines: [{ product_id: product.id, quantity: opts.warehouseStock }] } }));
  }
  await mgr.dispose();
  await wh.dispose();
  return { sku: product.sku, productId: product.id, resellerId: reseller.id, locationId: loc.id, locationCode: loc.code, warehouseId: whLoc.id };
}

export async function balance(locationId: number, productId: number) {
  const mgr = await apiAs(WM);
  const rows = await json<{ on_hand: number; reserved: number; available: number }[]>(
    await mgr.get(`/api/inventory/balances?location_id=${locationId}&product_id=${productId}&include_zero=true`));
  await mgr.dispose();
  return rows[0] ?? { on_hand: 0, reserved: 0, available: 0 };
}

type Loc = ReturnType<Page["locator"]>;

/** Select the first <option> whose text starts with the given prefix (e.g. a SKU or location code). */
export async function selectByPrefix(select: Loc, prefix: string) {
  // Shops are labelled dealer name first with the code at the end ("Roskill Tyres — Main shop (Auckland) · CODE");
  // other options still start with their code. Match the code as a whole word either way.
  const code = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const option = select.locator("option", { hasText: new RegExp(`(^|· )${code}( |$)`) }).first();
  await expect(option).toBeAttached();
  await select.selectOption((await option.getAttribute("value"))!);
}

/** Choose a product in a ProductSelect (searchable field) by typing the SKU and picking the match. */
export async function pickProduct(scope: Page | Loc, sku: string, nth = 0) {
  // Product pickers only: the top bar's "Search everything" box is a combobox too.
  const field = scope.locator('input[role="combobox"]:not([aria-label="Search everything"])').nth(nth);
  await field.click();
  await field.fill(sku);
  await scope.getByRole("option", { name: new RegExp(`^${sku} `) }).first().click();
  await expect(field).toHaveValue(new RegExp(`^${sku} `));
}
