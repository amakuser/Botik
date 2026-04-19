import { expect, test } from "./fixtures";

test("desktop-backed analytics read surface renders bounded fixture-backed analytics data", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/analytics");

  await expect(page.getByRole("heading", { name: "PnL / Аналитика" })).toBeVisible();
  await expect(page.getByTestId("analytics.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("analytics.summary.closed-trades")).toContainText("4");
  await expect(page.getByTestId("analytics.trade.0")).toContainText("XRPUSDT");
});
