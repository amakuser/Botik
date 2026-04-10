import { expect, test } from "./fixtures";

test("job monitor completes the fixed data backfill flow", async ({ page }) => {
  await page.goto("/jobs");

  await expect(page.getByRole("heading", { name: "Data Backfill Job" })).toBeVisible();
  await expect(page.getByTestId("jobs.backfill.interval")).toHaveText("1m");
  await page.getByRole("button", { name: "Start Data Backfill" }).click();

  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("data_backfill");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Bootstrapped DB for BTCUSDT/spot/1m.");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Fetched batch 1/4 for BTCUSDT/spot/1m.");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });
  await expect(page.getByTestId("jobs.selected.progress")).toHaveText("100%");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Data backfill completed: wrote 12 candles.");
});
