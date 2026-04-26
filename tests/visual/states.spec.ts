/**
 * State-specific visual tests.
 * Each test verifies a specific UI state that differs from the normal fixture state.
 * States are injected via page.route() or are already the fixture default.
 *
 * No user actions required — states are established before page.goto().
 *
 * Distinction from other suites:
 *   regression.spec — fixture "data loaded" state, full-page
 *   regions.spec    — fixture "data loaded" state, component-level
 *   states.spec (this) — specific states: error, empty, running, etc.
 */

import { expect, test } from "@playwright/test";
import { injectBackendError, injectMockResponse, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

// ── Empty state: jobs history ────────────────────────────────────────────────��
// GET /jobs returns [] by default in fixture backend — empty state is the fixture normal.

test("state: jobs history empty — empty message visible", async ({ page }) => {
  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  // Verify empty state element is present and readable
  const emptyMsg = page.getByTestId("jobs.history.empty");
  await expect(emptyMsg).toBeVisible();
  await expect(emptyMsg).toHaveText("Задач ещё не было.");

  // Region snapshot of the history panel in empty state
  const historyPanel = page.locator(".jobs-history-panel");
  await expect(historyPanel).toHaveScreenshot("state-jobs-history-empty.png");
});

// ── Error state: runtime page when GET /runtime-status returns 500 ────────────

test("state: runtime error banner when runtime-status endpoint fails", async ({ page }) => {
  await injectBackendError(page, "**/runtime-status");

  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  const banner = page.getByTestId("runtime.error.banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Не удалось загрузить");

  // Region snapshot of the error section
  const errorPanel = page.locator('[data-testid="runtime.error.banner"]').locator("..").locator("..");
  await expect(errorPanel).toHaveScreenshot("state-runtime-error-banner.png");
});

// ── Error state: telegram page when GET /telegram returns 500 ─────────────────

test("state: telegram error banner when telegram endpoint fails", async ({ page }) => {
  // Use port-specific pattern: **/telegram also matches the 4173 SPA route, breaking page load
  await injectBackendError(page, /127\.0\.0\.1:8765\/telegram$/);

  await page.goto(`${BASE}/telegram`);
  await waitForStableUI(page);

  const banner = page.getByTestId("telegram.error.banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Не удалось загрузить");

  const errorPanel = page.locator('[data-testid="telegram.error.banner"]').locator("..").locator("..");
  await expect(errorPanel).toHaveScreenshot("state-telegram-error-banner.png");
});

// ── Running state: health page pipeline when a runtime is running ─────────────

test("state: health pipeline shows running state when runtime is active", async ({ page }) => {
  const runningRuntimeFixture = {
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

  await injectMockResponse(page, "**/runtime-status", runningRuntimeFixture);
  await page.goto(`${BASE}/health`);
  await waitForStableUI(page);

  // Pipeline step 3 should show "Активно"
  const pipelineGrid = page.locator(".pipeline-grid");
  await expect(pipelineGrid).toBeVisible();

  // The third pipeline step should be in "running" state
  const tradingStep = pipelineGrid.locator(".pipeline-step").nth(2);
  await expect(tradingStep.locator(".pipeline-step__state")).toHaveText("Активно");

  // Region snapshot of pipeline in running state
  await expect(pipelineGrid).toHaveScreenshot("state-health-pipeline-running.png");
});

// ── Loading state approximation: verify loading text renders ─────────────────
// True loading-spinner capture is timing-dependent and unreliable.
// Instead we verify the loading placeholder TEXT is correct by delaying one endpoint.

test("state: health page shows loading text before data arrives", async ({ page }) => {
  // Delay all backend responses to keep the page in loading state during first render
  await page.route("**/health", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    await route.continue();
  });

  await page.goto(`${BASE}/health`);
  // Check for loading text BEFORE waitForStableUI (data not yet arrived)
  await expect(page.getByTestId("health.status")).toHaveText(/загрузка/, { timeout: 1_500 });
});

// ── HomePage: loading skeleton visible while data is in flight ───────────────
// HomePage now reads exclusively from /home/summary — single source of truth.

test("state: home loading skeleton visible", async ({ page }) => {
  // Delay /home/summary so the page renders skeletons before data arrives.
  await page.route(/127\.0\.0\.1:8765\/home\/summary$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    await route.continue();
  });

  await page.goto(`${BASE}/`);
  await expect(
    page.locator('[data-ui-role="skeleton"]').first(),
  ).toBeVisible({ timeout: 1_500 });
});

// ── HomePage: CRITICAL state shows the primary-action CTA ────────────────────

test("state: home critical state shows CTA", async ({ page }) => {
  const summaryFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    global: {
      state: "critical",
      health_score: 30,
      critical_reason: "1 незащищённая позиция",
      primary_action: { label: "Открыть диагностику", kind: "open-diagnostics" },
    },
    trading: {
      spot: { state: "running", lag_seconds: 1.0 },
      futures: { state: "running", lag_seconds: 1.0 },
      today_pnl: { value: 0, currency: "USDT", trend: "flat" },
      today_pnl_series: null,
    },
    risk: {
      positions_total: 1,
      by_state: {
        protected: 0,
        pending: 0,
        unprotected: 1,
        repairing: 0,
        failed: 0,
      },
      positions: [
        {
          id: "BTCUSDT-Buy",
          symbol: "BTCUSDT",
          side: "Buy",
          protection_state: "unprotected",
        },
      ],
    },
    reconciliation: {
      state: "healthy",
      last_run_at: "2026-01-01T00:00:00Z",
      last_run_age_seconds: 5,
      next_run_in_seconds: 55,
      drift_count: 0,
    },
    ml: {
      pipeline_state: "serving",
      active_model: { version: "v1", accuracy: 0.7, trained_at: "2026-01-01T00:00:00Z" },
      last_training_run: { scope: "spot", ended_at: "2026-01-01T00:00:00Z", status: "completed" },
    },
    connections: { bybit: null, telegram: null, database: "ok" },
    activity: [],
  };

  await injectMockResponse(page, /127\.0\.0\.1:8765\/home\/summary$/, summaryFixture);

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const hero = page.locator('[data-ui-role="hero-status"]');
  await expect(hero).toBeVisible({ timeout: 10_000 });
  await expect(hero).toHaveAttribute("data-ui-state", "critical", { timeout: 10_000 });

  const cta = page.locator('[data-ui-role="primary-action"][data-ui-action="open-diagnostics"]');
  await expect(cta).toBeVisible({ timeout: 10_000 });
  await expect(cta).toHaveAttribute("data-ui-state", "enabled");
});

// ── HomePage: complete backend failure surfaces error hero with retry ────────

test("state: home error — endpoint 500", async ({ page }) => {
  // /home/summary returns 500 → hero must enter error state with retry CTA.
  await injectBackendError(page, /127\.0\.0\.1:8765\/home\/summary$/);

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const hero = page.locator('[data-ui-role="hero-status"]');
  await expect(hero).toBeVisible({ timeout: 10_000 });
  await expect(hero).toHaveAttribute("data-ui-state", "critical", { timeout: 10_000 });

  const retry = page.locator('[data-ui-role="primary-action"][data-ui-action="retry"]');
  await expect(retry).toBeVisible({ timeout: 10_000 });
});

// ── HomePage: null bybit/telegram render literal "Недоступно" ────────────────

test('state: home — null bybit/telegram render "Недоступно"', async ({ page }) => {
  // bybit and telegram are deferred in this slice (always null from backend).
  // The Connections card MUST surface them as the literal text "Недоступно",
  // never inferred from any other endpoint.
  const summaryFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    global: {
      state: "healthy",
      health_score: 100,
      critical_reason: null,
      primary_action: null,
    },
    trading: {
      spot: { state: "running", lag_seconds: 0.5 },
      futures: { state: "running", lag_seconds: 0.5 },
      today_pnl: { value: 12.34, currency: "USDT", trend: "up" },
      today_pnl_series: null,
    },
    risk: {
      positions_total: 0,
      by_state: {
        protected: 0,
        pending: 0,
        unprotected: 0,
        repairing: 0,
        failed: 0,
      },
      positions: [],
    },
    reconciliation: {
      state: "healthy",
      last_run_at: "2026-01-01T00:00:00Z",
      last_run_age_seconds: 5,
      next_run_in_seconds: 55,
      drift_count: 0,
    },
    ml: {
      pipeline_state: "idle",
      active_model: null,
      last_training_run: null,
    },
    connections: { bybit: null, telegram: null, database: "ok" },
    activity: [],
  };

  await injectMockResponse(page, /127\.0\.0\.1:8765\/home\/summary$/, summaryFixture);

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const connections = page.locator('[data-ui-role="connections-card"]');
  await expect(connections).toBeVisible({ timeout: 10_000 });

  // Both Bybit and Telegram rows must render literal "Недоступно".
  await expect(connections).toContainText("Bybit");
  await expect(connections).toContainText("Telegram");
  // Two rows × literal text — count occurrences of "Недоступно" inside the card.
  const occurrences = await connections.evaluate((el) => {
    const text = el.textContent ?? "";
    return (text.match(/Недоступно/g) ?? []).length;
  });
  expect(
    occurrences,
    'connections card has at least 2 literal "Недоступно" entries (bybit + telegram)',
  ).toBeGreaterThanOrEqual(2);
});
