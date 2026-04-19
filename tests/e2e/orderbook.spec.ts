import { expect, test } from "./fixtures";

test("orderbook surface renders symbol selector and order book panels", async ({ page }) => {
  await page.goto("/orderbook");

  await expect(page.getByRole("heading", { name: "Стакан ордеров" })).toBeVisible();

  // Symbol controls exist
  await expect(page.getByRole("combobox")).toBeVisible();

  // Orderbook panel container
  await expect(page.getByTestId("orderbook.panel")).toBeVisible();

  // Refresh button
  await expect(page.getByRole("button", { name: /обновить/i })).toBeVisible();

  // No trading action buttons
  await expect(page.getByRole("button", { name: /buy|sell|start|stop runtime/i })).toHaveCount(0);
});
