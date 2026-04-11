import { expect, test } from "./fixtures";

test("analytics read surface renders bounded fixture-backed analytics data", async ({ page }) => {
  await page.goto("/analytics");

  await expect(page.getByRole("heading", { name: "PnL / Analytics" })).toBeVisible();
  await expect(page.getByTestId("analytics.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("analytics.summary.closed-trades")).toContainText("4");
  await expect(page.getByTestId("analytics.summary.win-rate")).toContainText("75.0%");
  await expect(page.getByTestId("analytics.summary.total-pnl")).toContainText("16.0000");
  await expect(page.getByTestId("analytics.equity.2026-04-11")).toBeVisible();
  await expect(page.getByTestId("analytics.trade.0")).toContainText("XRPUSDT");
  await expect(page.getByRole("button", { name: /start|stop|buy|sell|cancel|close/i })).toHaveCount(0);
});
