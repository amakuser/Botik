import { expect, test } from "./fixtures";

test("settings surface renders configuration panels and save controls", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  // Three configuration panels
  await expect(page.getByRole("heading", { name: "Bybit Demo" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bybit MainNet" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Telegram" })).toBeVisible();

  // Save action
  await expect(page.getByRole("button", { name: /save/i })).toBeVisible();

  // Test connection buttons (two — demo and mainnet)
  const testButtons = page.getByRole("button", { name: /test/i });
  await expect(testButtons).toHaveCount(2);

  // No destructive trading actions
  await expect(page.getByRole("button", { name: /buy|sell|start|stop runtime/i })).toHaveCount(0);
});
