import { expect, test } from "./fixtures";

test("desktop-backed models training control can start and stop bounded futures training", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/models");

  await expect(page.getByRole("button", { name: "Start Futures Training" })).toBeEnabled();
  await page.getByRole("button", { name: "Start Futures Training" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/starting|running|queued/i);

  await page.getByRole("link", { name: "Job Monitor" }).click();
  await expect(page.getByTestId("jobs.selected.job-type")).toContainText("training_control");

  await page.getByRole("link", { name: "Models / Status" }).click();
  await expect(page.getByRole("button", { name: "Stop Futures Training" })).toBeEnabled();
  await page.getByRole("button", { name: "Stop Futures Training" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/cancelled/i);
  await expect(page.getByTestId("models.run.0")).toContainText("cancelled");
});
