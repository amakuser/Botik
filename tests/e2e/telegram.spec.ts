import { expect, test } from "./fixtures";

test("telegram ops renders bounded fixture-backed operational data and safe connectivity check", async ({ page }) => {
  await page.goto("/telegram");

  await expect(page.getByRole("heading", { name: "Telegram Ops" })).toBeVisible();
  await expect(page.getByTestId("telegram.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("telegram.summary.allowed-chats")).toContainText("2");
  await expect(page.getByTestId("telegram.summary.alerts")).toContainText("1");
  await expect(page.getByTestId("telegram.summary.errors")).toContainText("1");
  await expect(page.getByTestId("telegram.command.0")).toBeVisible();
  await expect(page.getByTestId("telegram.alert.0")).toBeVisible();
  await expect(page.getByTestId("telegram.error.0")).toBeVisible();

  await page.getByTestId("telegram.connectivity-check").click();
  await expect(page.getByTestId("telegram.check.result")).toContainText("healthy");
  await expect(page.getByTestId("telegram.check.result")).toContainText("botik_fixture_bot");
  await expect(page.getByRole("button", { name: /start trading|stop trading|panic|resume|restart/i })).toHaveCount(0);
});
