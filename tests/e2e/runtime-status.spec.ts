import { expect, test } from "./fixtures";

test("runtime status renders fixture-backed spot and futures states", async ({ page }) => {
  await page.goto("/runtime");

  await expect(page.getByRole("heading", { name: "Runtime Status" })).toBeVisible();
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible();
  await expect(page.getByTestId("runtime.card.futures")).toBeVisible();
  await expect(page.getByTestId("runtime.state.spot")).toContainText("RUNNING");
  await expect(page.getByTestId("runtime.state.futures")).toContainText("DEGRADED");
  await expect(page.getByTestId("runtime.source.spot")).toContainText("fixture");
  await expect(page.getByRole("button", { name: /start/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /stop/i })).toHaveCount(0);
});
