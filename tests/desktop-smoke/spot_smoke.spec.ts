import { expect, test } from "./fixtures";

test("desktop-backed spot read surface renders bounded fixture-backed data", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/spot");

  await expect(page.getByRole("heading", { name: "Спот" })).toBeVisible();
  await expect(page.getByTestId("spot.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("spot.summary.balance-assets")).toContainText("2");
  await expect(page.getByTestId("spot.summary.holdings")).toContainText("2");
  await expect(page.getByTestId("spot.holding.BTCUSDT")).toBeVisible();
  await expect(page.getByTestId("spot.order.BTCUSDT")).toBeVisible();
  await expect(page.getByTestId("spot.fill.exec-1")).toBeVisible();
});
