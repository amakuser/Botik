import { expect, test } from "./fixtures";

test("desktop-backed runtime control can start and stop the fixture-backed spot runtime", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/runtime");

  const state = page.getByTestId("runtime.state.spot");
  const start = page.getByTestId("runtime.start.spot");
  const stop = page.getByTestId("runtime.stop.spot");

  await expect(state).toContainText("OFFLINE");
  await start.click();
  await expect(state).toContainText("RUNNING");
  await expect(page.getByTestId("runtime.pids.spot")).not.toContainText("нет");

  await stop.click();
  await expect(state).toContainText("OFFLINE");
  await expect(page.getByTestId("runtime.pids.spot")).toContainText("нет");
});
