import { expect, test } from "./fixtures";

test("backtest surface renders parameter form and run controls", async ({ page }) => {
  await page.goto("/backtest");

  await expect(page.getByRole("heading", { name: "Бэктест" })).toBeVisible();

  // Scope toggle buttons
  await expect(page.getByRole("button", { name: "Futures" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Spot" })).toBeVisible();

  // Run button
  await expect(page.getByRole("button", { name: /запустить бэктест/i })).toBeVisible();

  // Parameter inputs: days back and initial balance
  const numberInputs = page.locator("input[type='number']");
  await expect(numberInputs).toHaveCount(2);

  // No live trading buttons
  await expect(page.getByRole("button", { name: /buy|sell|start runtime|stop runtime/i })).toHaveCount(0);
});
