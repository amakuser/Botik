/**
 * Pixel-regression suite — six high-value pages compared against committed baselines.
 * Baselines live in tests/visual/baselines/*.png (platform-independent, committed to git).
 *
 * First run (no baselines yet): npx playwright test --config tests/visual/playwright.visual.config.ts --update-snapshots
 * Normal run: npx playwright test --config tests/visual/playwright.visual.config.ts
 * After intentional UI change: scripts/update-visual-baselines.ps1
 */

import { expect, test } from "@playwright/test";
import { getDynamicMasks, injectMockResponse, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

// Stable models fixture — prevents latest_run_scope/status changes (from job runs)
// from breaking the baseline; these fields appear in unmasked status-caption elements.
const MODELS_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "fixture",
  summary: {
    total_models: 0,
    active_declared_count: 0,
    ready_scopes: 0,
    recent_training_runs_count: 0,
    latest_run_scope: "not available",
    latest_run_status: "not available",
    latest_run_mode: "not available",
    manifest_status: "missing",
    db_available: false,
  },
  scopes: [],
  registry_entries: [],
  recent_training_runs: [],
  truncated: { registry_entries: false, recent_training_runs: false },
};

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
    if (name === "models") {
      await injectMockResponse(page, "**/models", MODELS_FIXTURE);
    }

    await page.goto(`${BASE}${url}`);
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot(`${name}.png`, {
      mask: getDynamicMasks(page),
      fullPage: true,
    });
  });
}
