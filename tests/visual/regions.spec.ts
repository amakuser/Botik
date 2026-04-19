/**
 * Region / component visual baselines.
 * Full-page screenshots are too coarse for detecting component-level regressions.
 * This suite snapshots specific high-value regions at the component level.
 *
 * Update after intentional component changes: scripts/update-visual-baselines.ps1
 */

import { expect, test } from "@playwright/test";
import { injectMockResponse, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

// ── Runtime cards (offline/fixture state) ─────────────────────────────────────

test("region: runtime spot card (offline state)", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  const card = page.getByTestId("runtime.card.spot");
  await expect(card).toBeVisible();

  // No masking needed: fixture returns stable "n/a" values and "fixture" source
  await expect(card).toHaveScreenshot("region-runtime-spot-offline.png");
});

test("region: runtime futures card (offline state)", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  const card = page.getByTestId("runtime.card.futures");
  await expect(card).toBeVisible();

  await expect(card).toHaveScreenshot("region-runtime-futures-offline.png");
});

// ── Job preset cards (static content, no dynamic data) ────────────────────────

test("region: job backfill preset card", async ({ page }) => {
  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  const card = page.getByTestId("job.preset.data-backfill");
  await expect(card).toBeVisible();

  await expect(card).toHaveScreenshot("region-job-backfill-card.png");
});

test("region: job integrity preset card", async ({ page }) => {
  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  const card = page.getByTestId("job.preset.data-integrity");
  await expect(card).toBeVisible();

  await expect(card).toHaveScreenshot("region-job-integrity-card.png");
});

// ── Health page metric grid (mask live values, preserve card structure) ────────

test("region: health metric cards grid", async ({ page }) => {
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const grid = page.locator(".home-metrics-grid");
  await expect(grid).toBeVisible();

  // Mask the numeric values — they come from live fixture endpoints and are fixed
  // but structurally card layout, label text, and sub text are what we're protecting
  await expect(grid).toHaveScreenshot("region-health-metrics-grid.png", {
    mask: [page.locator(".home-metric-card__value"), page.locator(".home-metric-card__sub")],
  });
});

// ── Health page pipeline section (mask runtime-dependent state labels) ─────────

test("region: health pipeline section", async ({ page }) => {
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const pipeline = page.locator(".pipeline-grid");
  await expect(pipeline).toBeVisible();

  // Mask state label and description text since they depend on runtime state
  await expect(pipeline).toHaveScreenshot("region-health-pipeline.png", {
    mask: [page.locator(".pipeline-step__state"), page.locator(".pipeline-step__desc")],
  });
});

// ── Telegram summary cards grid (mask numeric counters and note text) ──────────

test("region: telegram summary grid", async ({ page }) => {
  await page.goto(`${BASE}/telegram`);
  await waitForStableUI(page);

  const grid = page.locator(".telegram-summary-grid");
  await expect(grid).toBeVisible();

  // Mask values and notes (connectivity state text, counts, last-message snippets)
  await expect(grid).toHaveScreenshot("region-telegram-summary-grid.png", {
    mask: [
      page.locator(".telegram-summary-card__value"),
      page.locator(".telegram-summary-card__note"),
    ],
  });
});

// ── Titlebar (requires VITE_BOTIK_DESKTOP=true — desktop-smoke env) ───────────
// Note: in the standard visual suite the desktop titlebar renders because
// the preview server is started with VITE_BOTIK_DESKTOP=true by test-desktop-smoke.ps1.
// If running against a non-desktop build the titlebar is not present and this test is skipped.

test("region: desktop titlebar chrome", async ({ page }) => {
  await page.goto(BASE);
  await waitForStableUI(page);

  const titlebar = page.getByTestId("foundation.desktop-titlebar");
  const isVisible = await titlebar.isVisible();

  if (!isVisible) {
    test.skip();
    return;
  }

  // Mask the bot-dot (may pulse if a runtime is running) and the route-context text
  await expect(titlebar).toHaveScreenshot("region-desktop-titlebar.png", {
    mask: [
      page.locator(".desktop-frame__bot-dot"),
      page.getByTestId("foundation.desktop-route-context"),
    ],
  });
});

// ── Runtime running state card (via mocked response) ─────────────────────────

test("region: runtime spot card (running state, mocked)", async ({ page }) => {
  const runningFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    runtimes: [
      {
        runtime_id: "spot",
        label: "Spot Runtime",
        state: "running",
        pids: [99999],
        pid_count: 1,
        last_heartbeat_at: "2026-01-01T00:00:00Z",
        last_heartbeat_age_seconds: 3.0,
        last_error: null,
        last_error_at: null,
        status_reason: "process present with recent heartbeat activity",
        source_mode: "fixture",
      },
      {
        runtime_id: "futures",
        label: "Futures Runtime",
        state: "offline",
        pids: [],
        pid_count: 0,
        last_heartbeat_at: null,
        last_heartbeat_age_seconds: null,
        last_error: null,
        last_error_at: null,
        status_reason: "no matching runtime process detected",
        source_mode: "fixture",
      },
    ],
  };

  await injectMockResponse(page, "**/runtime-status", runningFixture);
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  const card = page.getByTestId("runtime.card.spot");
  await expect(page.getByTestId("runtime.state.spot")).toHaveText("RUNNING");

  // Mask dynamic timestamp fields; heartbeat age (3.0 → "3s ago") and PID are stable in mock
  await expect(card).toHaveScreenshot("region-runtime-spot-running.png", {
    mask: [
      page.getByTestId("runtime.heartbeat.spot"),
      page.getByTestId("runtime.pids.spot"),
      card.locator("dl dd"),
    ],
  });
});
