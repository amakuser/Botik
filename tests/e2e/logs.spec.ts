import { expect, test } from "./fixtures";

test("unified logs shows approved channels and streams job log entries", async ({ page, request }) => {
  await page.goto("/logs");

  await expect(page.getByRole("heading", { name: "Логи" })).toBeVisible();
  await expect(page.getByTestId("logs.channel.app")).toBeVisible();
  await expect(page.getByTestId("logs.channel.jobs")).toBeVisible();
  await expect(page.getByTestId("logs.channel.desktop")).toBeVisible();
  await expect(page.getByTestId("logs.channel.telegram")).toHaveCount(0);

  await page.getByTestId("logs.channel.jobs").click();

  const response = await request.post("http://127.0.0.1:8765/jobs", {
    headers: {
      "x-botik-session-token": "botik-dev-token",
      "content-type": "application/json",
    },
    data: {
      job_type: "sample_data_import",
      payload: {
        sleep_ms: 80,
      },
    },
  });

  expect(response.ok()).toBeTruthy();
  await expect(page.getByTestId("logs.viewer.list")).toContainText("Started job sample_data_import.", { timeout: 15000 });
});
