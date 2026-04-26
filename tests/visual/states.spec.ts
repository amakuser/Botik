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

test("state: home loading skeleton visible", async ({ page }) => {
  // Delay every endpoint the home page reads. Slow but bounded — the page
  // must show skeletons before the data arrives.
  const ENDPOINTS = [
    /127\.0\.0\.1:8765\/health$/,
    /127\.0\.0\.1:8765\/runtime-status$/,
    /127\.0\.0\.1:8765\/spot$/,
    /127\.0\.0\.1:8765\/futures$/,
    /127\.0\.0\.1:8765\/models$/,
    /127\.0\.0\.1:8765\/telegram$/,
    /127\.0\.0\.1:8765\/diagnostics$/,
    /127\.0\.0\.1:8765\/jobs$/,
  ];
  for (const pattern of ENDPOINTS) {
    await page.route(pattern, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      await route.continue();
    });
  }

  await page.goto(`${BASE}/`);
  // A skeleton element must render BEFORE the data settles.
  await expect(
    page.locator('[data-ui-role="skeleton"]').first(),
  ).toBeVisible({ timeout: 1_500 });
});

// ── HomePage: CRITICAL state shows the primary-action CTA ────────────────────

test("state: home critical state shows CTA", async ({ page }) => {
  // Mock /futures so it returns one unprotected position — derived state
  // must classify the system as CRITICAL and surface the primary CTA.
  const futuresFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    source_mode: "fixture",
    summary: {
      account_type: "UNIFIED",
      positions_count: 1,
      protected_positions_count: 0,
      attention_positions_count: 0,
      recovered_positions_count: 0,
      open_orders_count: 0,
      recent_fills_count: 0,
      unrealized_pnl_total: 0,
    },
    positions: [
      {
        account_type: "UNIFIED",
        symbol: "BTCUSDT",
        side: "Buy",
        position_idx: 0,
        margin_mode: "REGULAR_MARGIN",
        leverage: 5,
        qty: 0.01,
        entry_price: 60000,
        mark_price: 60000,
        liq_price: 50000,
        unrealized_pnl: 0,
        take_profit: null,
        stop_loss: null,
        protection_status: "unprotected",
        source_of_truth: "exchange",
        recovered_from_exchange: false,
        strategy_owner: null,
        updated_at_utc: "2026-01-01T00:00:00Z",
      },
    ],
    active_orders: [],
    recent_fills: [],
  };

  await injectMockResponse(page, /127\.0\.0\.1:8765\/futures$/, futuresFixture);

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const hero = page.locator('[data-ui-role="hero-status"]');
  await expect(hero).toBeVisible({ timeout: 10_000 });
  await expect(hero).toHaveAttribute("data-ui-state", "critical", { timeout: 10_000 });

  const cta = page.locator('[data-ui-role="primary-action"][data-ui-action="open-futures"]');
  await expect(cta).toBeVisible({ timeout: 10_000 });
  await expect(cta).toHaveAttribute("data-ui-state", "enabled");
});

// ── HomePage: complete backend failure surfaces error hero with retry ────────

test("state: home error — endpoint 500", async ({ page }) => {
  // Inject a 500 on every endpoint the home page reads. With every query
  // failing, the hero must switch to the error state and expose a retry CTA.
  const ENDPOINTS = [
    /127\.0\.0\.1:8765\/health$/,
    /127\.0\.0\.1:8765\/runtime-status$/,
    /127\.0\.0\.1:8765\/spot$/,
    /127\.0\.0\.1:8765\/futures$/,
    /127\.0\.0\.1:8765\/models$/,
    /127\.0\.0\.1:8765\/telegram$/,
    /127\.0\.0\.1:8765\/diagnostics$/,
    /127\.0\.0\.1:8765\/jobs$/,
  ];
  for (const pattern of ENDPOINTS) {
    await injectBackendError(page, pattern);
  }

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const hero = page.locator('[data-ui-role="hero-status"]');
  await expect(hero).toBeVisible({ timeout: 10_000 });
  // The error hero is rendered with state "critical" and contains the retry button.
  await expect(hero).toHaveAttribute("data-ui-state", "critical", { timeout: 10_000 });

  const retry = page.locator('[data-ui-role="primary-action"][data-ui-action="retry"]');
  await expect(retry).toBeVisible({ timeout: 10_000 });
});
