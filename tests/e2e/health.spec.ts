import { expect, test } from "./fixtures";

test("foundation health route renders bootstrap data", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Botik Foundation" })).toBeVisible();
  await expect(page.getByTestId("health.status")).toContainText("ok");
  await expect(page.getByTestId("bootstrap.app-name")).toContainText("Botik Foundation");
});
