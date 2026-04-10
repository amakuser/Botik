import { expect, test } from "./fixtures";

test("job monitor completes the sample import flow", async ({ page }) => {
  await page.goto("/jobs");

  await expect(page.getByRole("heading", { name: "Data Jobs" })).toBeVisible();
  await page.getByRole("button", { name: "Start Sample Import" }).click();

  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("sample_data_import");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Starting sample data import for 6 rows.");
  await expect(page.getByTestId("jobs.selected.state")).toHaveText("completed", { timeout: 15000 });
  await expect(page.getByTestId("jobs.selected.progress")).toHaveText("100%");
  await expect(page.getByTestId("jobs.logs.list")).toContainText("Sample data import completed.");
});
