import { expect, test } from "./fixtures";

test("desktop-backed models registry and training status surface renders fixture-backed data", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/models");

  await expect(page.getByRole("heading", { name: "Models Registry / Training Status" })).toBeVisible();
  await expect(page.getByTestId("models.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("models.summary.total-models")).toContainText("3");
  await expect(page.getByTestId("models.scope.spot")).toContainText("spot-champion-v3");
  await expect(page.getByTestId("models.scope.futures")).toContainText("futures-paper-v2");
  await expect(page.getByTestId("models.registry.0")).toContainText("futures-paper-v2");
  await expect(page.getByTestId("models.run.0")).toContainText("run-futures-1");
  await expect(page.getByRole("button", { name: "Start Futures Training" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop Futures Training" })).toBeDisabled();
});
