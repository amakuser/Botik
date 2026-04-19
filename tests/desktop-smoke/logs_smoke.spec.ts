import { expect, test } from "./fixtures";

test("desktop-backed unified logs renders desktop channel events", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/logs");

  await expect(page.getByRole("heading", { name: "Логи" })).toBeVisible();
  await page.getByTestId("logs.channel.desktop").click();

  await expect(page.getByTestId("logs.status.channel")).toContainText("Desktop Shell");
  await expect(page.getByTestId("logs.viewer.list")).toContainText("ready", { timeout: 15000 });
});
