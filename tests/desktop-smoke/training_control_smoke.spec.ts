import { expect, test } from "./fixtures";

test("desktop-backed models training control can start and stop bounded futures training", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/models");

  await expect(page.getByRole("button", { name: "Запустить обучение" })).toBeEnabled();
  await page.getByRole("button", { name: "Запустить обучение" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/starting|running|queued/i);

  await page.getByRole("link", { name: "Мониторинг задач" }).click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("training_control");

  await page.getByRole("link", { name: "Модели" }).click();
  await expect(page.getByRole("button", { name: "Остановить обучение" })).toBeEnabled();
  await page.getByRole("button", { name: "Остановить обучение" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/cancelled/i);
  await expect(page.getByTestId("models.run.0")).toContainText("cancelled");
});
