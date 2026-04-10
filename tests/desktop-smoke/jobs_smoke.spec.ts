import { expect, test } from "./fixtures";

test("desktop-backed job monitor can start and stop the sample import", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/jobs");

  await expect(page.getByRole("heading", { name: "Data Jobs" })).toBeVisible();
  await page.getByRole("button", { name: "Start Sample Import" }).click();

  await expect(page.getByTestId("jobs.logs.list")).toContainText("Starting sample data import for 6 rows.");
  await expect(page.getByRole("button", { name: "Stop Selected Job" })).toBeEnabled();
  await page.getByRole("button", { name: "Stop Selected Job" }).click();

  await expect(page.getByTestId("jobs.selected.state")).toHaveText("cancelled", { timeout: 15000 });
});
