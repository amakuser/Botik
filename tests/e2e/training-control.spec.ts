import { expect, test } from "./fixtures";

test("models training control can start and stop the bounded futures training flow", async ({ page }) => {
  await page.goto("/models");

  await expect(page.getByRole("button", { name: "Start Futures Training" })).toBeEnabled();
  await page.getByRole("button", { name: "Start Futures Training" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/starting|running|queued/i);

  await page.getByRole("link", { name: "Job Monitor" }).click();
  await expect(page.getByText("training_control")).toBeVisible();

  await page.getByRole("link", { name: "Models / Status" }).click();
  await expect(page.getByRole("button", { name: "Stop Futures Training" })).toBeEnabled();
  await page.getByRole("button", { name: "Stop Futures Training" }).click();

  await expect(page.getByTestId("models.training-control.state")).toContainText(/cancelled/i);
  await expect(page.getByTestId("models.run.0")).toContainText("cancelled");
});
