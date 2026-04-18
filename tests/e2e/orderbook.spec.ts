import { expect, test } from "./fixtures";

test("orderbook surface renders symbol selector and order book panels", async ({ page }) => {
  await page.goto("/orderbook");

  await expect(page.getByRole("heading", { name: "Order Book" })).toBeVisible();

  // Symbol controls exist
  await expect(page.getByRole("combobox")).toBeVisible();

  // Orderbook panel container
  await expect(page.getByTestId("orderbook.panel")).toBeVisible();

  // Refresh button
  await expect(page.getByRole("button", { name: /refresh/i })).toBeVisible();

  // No trading action buttons
  await expect(page.getByRole("button", { name: /buy|sell|start|stop runtime/i })).toHaveCount(0);
});
