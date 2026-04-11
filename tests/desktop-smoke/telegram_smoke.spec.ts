import { expect, test } from "./fixtures";

test("desktop-backed telegram ops renders bounded fixture-backed status and safe connectivity check", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/telegram");

  await expect(page.getByRole("heading", { name: "Telegram Ops" })).toBeVisible();
  await expect(page.getByTestId("telegram.source-mode")).toContainText("fixture");
  await expect(page.getByTestId("telegram.summary.allowed-chats")).toContainText("2");
  await expect(page.getByTestId("telegram.command.0")).toBeVisible();
  await page.getByTestId("telegram.connectivity-check").click();
  await expect(page.getByTestId("telegram.check.result")).toContainText("healthy");
});
