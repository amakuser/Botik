import { expect, test } from "./fixtures";

test("job monitor validates data integrity after the fixed backfill flow", async ({ page }) => {
  await page.goto("/jobs");

  const startBackfill = page.getByRole("button", { name: "Start Data Backfill" });
  await expect(startBackfill).toBeVisible();
  await startBackfill.click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("data_backfill");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });

  await expect(page.getByRole("button", { name: "Start Data Integrity" })).toBeVisible();
  await page.getByRole("button", { name: "Start Data Integrity" }).click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("data_integrity");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Validated symbol_registry candle_count=12");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Validated chronological range");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });
  await expect(page.getByTestId("jobs.selected.progress")).toHaveText("100%");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Data integrity check completed: validated 12 candles.");
});
