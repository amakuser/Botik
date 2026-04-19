import { expect, test } from "./fixtures";

test("futures read surface renders bounded fixture-backed futures data", async ({ page }) => {
  await page.goto("/futures");

  await expect(page.getByRole("heading", { name: "Фьючерсы" })).toBeVisible();
  await expect(page.getByTestId("futures.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("futures.summary.positions")).toContainText("2");
  await expect(page.getByTestId("futures.summary.recovered")).toContainText("1");
  await expect(page.getByTestId("futures.summary.orders")).toContainText("1");
  await expect(page.getByTestId("futures.summary.fills")).toContainText("1");
  await expect(page.getByTestId("futures.position.ETHUSDT.Buy")).toBeVisible();
  await expect(page.getByTestId("futures.position.BTCUSDT.Sell")).toBeVisible();
  await expect(page.getByTestId("futures.order.ETHUSDT")).toBeVisible();
  await expect(page.getByTestId("futures.fill.fut-exec-1")).toBeVisible();
  await expect(page.getByRole("button", { name: /start|stop|close|cancel|buy|sell/i })).toHaveCount(0);
});
