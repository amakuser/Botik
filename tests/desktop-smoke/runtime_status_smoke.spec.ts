import { expect, test } from "./fixtures";

test("desktop-backed runtime status renders fixture-backed states", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/runtime");

  await expect(page.getByRole("heading", { name: "Runtime Status" })).toBeVisible();
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible();
  await expect(page.getByTestId("runtime.card.futures")).toBeVisible();
  await expect(page.getByTestId("runtime.state.spot")).toContainText("RUNNING");
  await expect(page.getByTestId("runtime.state.futures")).toContainText("DEGRADED");
  await expect(page.getByRole("button", { name: /start/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /stop/i })).toHaveCount(0);
});
