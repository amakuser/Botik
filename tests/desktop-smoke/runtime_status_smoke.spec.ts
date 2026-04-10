import { expect, test } from "./fixtures";

test("desktop-backed runtime status renders fixture-backed states", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/runtime");

  await expect(page.getByRole("heading", { name: "Runtime Control" })).toBeVisible();
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible();
  await expect(page.getByTestId("runtime.card.futures")).toBeVisible();
  await expect(page.getByTestId("runtime.state.spot")).toContainText("OFFLINE");
  await expect(page.getByTestId("runtime.state.futures")).toContainText("OFFLINE");
  await expect(page.getByTestId("runtime.start.spot")).toBeEnabled();
  await expect(page.getByTestId("runtime.stop.spot")).toBeDisabled();
});
