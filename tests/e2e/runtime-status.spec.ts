import { expect, test } from "./fixtures";

test("runtime status renders fixture-backed spot and futures states", async ({ page }) => {
  await page.goto("/runtime");

  await expect(page.getByRole("heading", { name: "Управление рантаймом" })).toBeVisible();
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible();
  await expect(page.getByTestId("runtime.card.futures")).toBeVisible();
  await expect(page.getByTestId("runtime.state.spot")).toContainText("OFFLINE");
  await expect(page.getByTestId("runtime.state.futures")).toContainText("OFFLINE");
  await expect(page.getByTestId("runtime.source.spot")).toContainText("fixture");
  await expect(page.getByTestId("runtime.start.spot")).toBeEnabled();
  await expect(page.getByTestId("runtime.stop.spot")).toBeDisabled();
});
