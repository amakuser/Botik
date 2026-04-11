import { expect, test } from "./fixtures";

test("spot read surface renders bounded fixture-backed spot data", async ({ page }) => {
  await page.goto("/spot");

  await expect(page.getByRole("heading", { name: "Spot Read Surface" })).toBeVisible();
  await expect(page.getByTestId("spot.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("spot.summary.balance-assets")).toContainText("2");
  await expect(page.getByTestId("spot.summary.holdings")).toContainText("2");
  await expect(page.getByTestId("spot.summary.orders")).toContainText("1");
  await expect(page.getByTestId("spot.summary.fills")).toContainText("1");
  await expect(page.getByTestId("spot.summary.intents")).toContainText("1");
  await expect(page.getByTestId("spot.holding.BTCUSDT")).toBeVisible();
  await expect(page.getByTestId("spot.order.BTCUSDT")).toBeVisible();
  await expect(page.getByTestId("spot.fill.exec-1")).toBeVisible();
  await expect(page.getByRole("button", { name: /sell|cancel|start|stop/i })).toHaveCount(0);
});
