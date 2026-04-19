import { expect, test } from "./fixtures";

test("desktop-backed job monitor can start and stop the sample import", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/jobs");

  await expect(page.getByRole("heading", { name: "Задачи данных" })).toBeVisible();
  await page.getByRole("button", { name: "Запустить импорт" }).click();

  await expect(page.getByTestId("jobs.logs.list")).toContainText("Starting sample data import for 6 rows.");
  await expect(page.getByRole("button", { name: "Остановить задачу" })).toBeEnabled();
  await page.getByRole("button", { name: "Остановить задачу" }).click();

  await expect(page.getByTestId("jobs.selected.state")).toHaveText("cancelled", { timeout: 15000 });
});
