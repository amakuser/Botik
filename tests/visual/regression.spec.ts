/**
 * Pixel-regression suite — six high-value pages compared against committed baselines.
 * Baselines live in tests/visual/baselines/*.png (platform-independent, committed to git).
 *
 * First run (no baselines yet): npx playwright test --config tests/visual/playwright.visual.config.ts --update-snapshots
 * Normal run: npx playwright test --config tests/visual/playwright.visual.config.ts
 * After intentional UI change: scripts/update-visual-baselines.ps1
 */

import { expect, test } from "@playwright/test";
import { getDynamicMasks, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

const SNAPSHOT_PAGES = [
  { name: "health",    url: "/" },
  { name: "spot",      url: "/spot" },
  { name: "futures",   url: "/futures" },
  { name: "analytics", url: "/analytics" },
  { name: "models",    url: "/models" },
  { name: "jobs",      url: "/jobs" },
];

for (const { name, url } of SNAPSHOT_PAGES) {
  test(`visual: ${name} — pixel regression`, async ({ page }) => {
    await page.goto(`${BASE}${url}`);
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot(`${name}.png`, {
      mask: getDynamicMasks(page),
      fullPage: true,
    });
  });
}
