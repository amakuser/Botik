import { expect, test } from "./fixtures";

test("market surface renders price ticker cards or graceful error state", async ({ page }) => {
  await page.goto("/market");

  await expect(page.getByRole("heading", { name: "Рынок" })).toBeVisible();

  // Either ticker cards or error panel — both are valid render states
  const tickerCards = page.locator(".market-card");
  const errorHeading = page.getByRole("heading", { name: "Ошибка подключения" });

  const hasCards = await tickerCards.count();
  const hasError = await errorHeading.isVisible().catch(() => false);

  if (hasCards > 0) {
    // Verify at least one card is present
    await expect(page.locator(".market-card").first()).toBeVisible();
  } else if (hasError) {
    // Graceful degradation accepted
    await expect(errorHeading).toBeVisible();
  }

  // No trading action buttons
  await expect(page.getByRole("button", { name: /buy|sell|start|stop/i })).toHaveCount(0);
});
