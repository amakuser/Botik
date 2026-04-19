import { expect, test } from "./fixtures";

test("desktop-backed job monitor validates data integrity after the fixed backfill flow", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/jobs");

  const startBackfill = page.getByRole("button", { name: "Запустить загрузку" });
  await expect(startBackfill).toBeVisible();
  await startBackfill.click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("data_backfill");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });

  await expect(page.getByRole("button", { name: "Запустить проверку" })).toBeVisible();
  await page.getByRole("button", { name: "Запустить проверку" }).click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("data_integrity");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Validated symbol_registry candle_count=12");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });
  await expect(page.getByTestId("jobs.selected.progress")).toHaveText("100%");
});
