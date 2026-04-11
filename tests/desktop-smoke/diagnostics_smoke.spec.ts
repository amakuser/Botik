import { expect, test } from "./fixtures";

test("desktop-backed diagnostics compatibility surface renders bounded resolved config and paths", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/diagnostics");

  await expect(page.getByRole("heading", { name: "Settings / Diagnostics Compatibility" })).toBeVisible();
  await expect(page.getByTestId("diagnostics.source-mode")).toContainText("resolved");
  await expect(page.getByTestId("diagnostics.summary.routes")).toContainText("10");
  await expect(page.getByTestId("diagnostics.summary.fixtures")).toContainText("7");
  await expect(page.getByTestId("diagnostics.path.runtime_status_fixture")).toContainText("fixture");
  await expect(page.getByText("Runtime control is currently configured in fixture mode.")).toBeVisible();
});
