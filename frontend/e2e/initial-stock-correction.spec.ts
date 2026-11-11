import { expect, test } from "@playwright/test";
import { apiAs, json, login, RM, setup, WM } from "./helpers";

// UAT: a dealer's initial stock was entered wrongly. The Relationship Manager corrects it with a reason; the original
// entry stays, the correction shows beside it and in Reports → Stock corrections. The Warehouse Manager can't correct.

test("the RM corrects a wrongly entered initial stock; the original is kept and the correction is reported", async ({ page }) => {
  const f = await setup({ resellerStock: 6, warehouseStock: 0, tag: "ISC" });
  await login(page, RM);
  await page.goto(`/resellers/${f.resellerId}`);
  await page.getByRole("tab", { name: "Dealer history" }).click();
  await page.getByRole("button", { name: "Correct initial stock" }).click();
  const dialog = page.getByRole("dialog", { name: /Correct initial stock/ });
  await dialog.getByLabel(`Correct quantity for ${f.sku}`).fill("2");
  await dialog.getByLabel(/What was wrong\?/).fill("Typed 6 instead of 2 while serving a customer");
  await expect(dialog.getByText(`${f.sku} 6 → 2`)).toBeVisible();
  await dialog.getByRole("button", { name: /^Save correction/ }).click();
  await expect(dialog).toBeHidden();

  // Beside the original entry: the correction, who and why. The onboarding stock shows both figures.
  await expect(page.getByText(`${f.sku} 6 → 2`)).toBeVisible();
  await expect(page.getByText("Reason: Typed 6 instead of 2 while serving a customer")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "After corrections" })).toBeVisible();
  const rm = await apiAs(RM);
  const [bal] = await json<{ on_hand: number }[]>(
    await rm.get(`/api/inventory/balances?location_id=${f.locationId}&product_id=${f.productId}`));
  expect(bal.on_hand).toBe(2);
  await rm.dispose();

  // Reports → Stock corrections.
  await page.goto("/reports");
  await page.getByRole("tab", { name: "Stock corrections" }).click();
  await expect(page.getByRole("table", { name: "Stock corrections" })).toContainText(f.sku);

  // The Warehouse Manager sees the dealer history but can't correct it.
  await login(page, WM);
  await page.goto(`/resellers/${f.resellerId}`);
  await page.getByRole("tab", { name: "Dealer history" }).click();
  await expect(page.getByText("Onboarded with this stock")).toBeVisible();
  await expect(page.getByRole("button", { name: "Correct initial stock" })).toHaveCount(0);
});
