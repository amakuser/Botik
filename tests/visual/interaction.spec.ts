/**
 * Interaction-aware visual tests.
 * Each test performs a user action and verifies the visible UI result.
 *
 * Distinction from other suites:
 *   layout.spec     — no actions, JS geometry checks
 *   regression.spec — no actions, full-page pixel diff
 *   regions.spec    — no actions, component-level pixel diff
 *   states.spec     — no actions, mocked fixture state on page load
 *   interaction.spec (this file) — button click → verify visible result
 */

import { expect, test } from "@playwright/test";
import { injectBackendError, injectMockResponse, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

// ── Telegram: check button → result panel ─────────────────────────────────────

test("interaction: telegram check → result panel appears with state label", async ({ page }) => {
  await page.goto(`${BASE}/telegram`);
  await waitForStableUI(page);

  // Before: result panel is absent
  await expect(page.getByTestId("telegram.check.result")).not.toBeVisible();

  // Action
  await page.getByTestId("telegram.connectivity-check").click();

  // After: wait for result panel to render
  await expect(page.getByTestId("telegram.check.result")).toBeVisible({ timeout: 10_000 });

  // Verify visible content — state label is present (not masked)
  const result = page.getByTestId("telegram.check.result");
  await expect(result.locator("strong")).toBeVisible();

  // Region snapshot — mask the latency badge and bot metadata (dynamic numbers)
  await expect(result).toHaveScreenshot("telegram-check-result.png", {
    mask: [page.locator(".telegram-check-result__meta")],
  });
});

// ── Jobs: start job fails → action error banner ───────────────────────────────

test("interaction: jobs start fails → action error banner appears", async ({ page }) => {
  // Intercept the POST /jobs endpoint to return a 422 error before we click
  await page.route("**/jobs", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Test: simulated start failure" }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  // Before: no error banner
  await expect(page.getByTestId("jobs.action-error")).not.toBeVisible();

  // Action: click the backfill start button
  await page.getByTestId("job.preset.data-backfill").getByRole("button").click();

  // After: error banner appears
  await expect(page.getByTestId("jobs.action-error")).toBeVisible({ timeout: 5_000 });

  // Region snapshot of the error section
  const errorSection = page.locator(".jobs-main .panel").last();
  await expect(errorSection).toHaveScreenshot("jobs-action-error-banner.png");
});

// ── Runtime: start → state transitions to running (mocked) ───────────────────

test("interaction: runtime start → card shows RUNNING state after action", async ({ page }) => {
  // Fully mock both states so the test doesn't depend on real backend state.
  const offlineFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    runtimes: [
      {
        runtime_id: "spot", label: "Spot Runtime", state: "offline",
        pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
        last_error: null, last_error_at: null, status_reason: "no matching runtime process detected",
        source_mode: "fixture",
      },
      {
        runtime_id: "futures", label: "Futures Runtime", state: "offline",
        pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
        last_error: null, last_error_at: null, status_reason: "no matching runtime process detected",
        source_mode: "fixture",
      },
    ],
  };

  const runningFixture = {
    generated_at: "2026-01-01T00:00:00Z",
    runtimes: [
      {
        runtime_id: "spot", label: "Spot Runtime", state: "running",
        pids: [99999], pid_count: 1, last_heartbeat_at: "2026-01-01T00:00:00Z",
        last_heartbeat_age_seconds: 3.0, last_error: null, last_error_at: null,
        status_reason: "process present with recent heartbeat activity", source_mode: "fixture",
      },
      {
        runtime_id: "futures", label: "Futures Runtime", state: "offline",
        pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
        last_error: null, last_error_at: null, status_reason: "no matching runtime process detected",
        source_mode: "fixture",
      },
    ],
  };

  // Before start: always return offline state
  let startCalled = false;
  await page.route("**/runtime-status", async (route) => {
    const body = startCalled ? runningFixture : offlineFixture;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.route("**/runtime-control/spot/start", async (route) => {
    startCalled = true;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify(runningFixture.runtimes[0]),
    });
  });

  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  // Before: start button enabled, stop disabled
  await expect(page.getByTestId("runtime.start.spot")).toBeEnabled();
  await expect(page.getByTestId("runtime.stop.spot")).toBeDisabled();

  // Action
  await page.getByTestId("runtime.start.spot").click();

  // After: state indicator shows RUNNING, stop button enabled
  await expect(page.getByTestId("runtime.state.spot")).toHaveText("RUNNING", { timeout: 5_000 });
  await expect(page.getByTestId("runtime.stop.spot")).toBeEnabled();

  // Region snapshot of the spot card in running state — mask dynamic timestamp/PID fields
  const card = page.getByTestId("runtime.card.spot");
  await expect(card).toHaveScreenshot("runtime-card-running-state.png", {
    mask: [
      page.getByTestId("runtime.heartbeat.spot"),
      page.getByTestId("runtime.pids.spot"),
      card.locator("dl dd"),  // timestamps in details
    ],
  });
});

// ── Navigation: sidebar active state after route change ───────────────────────

test("interaction: sidebar nav shows correct active link after navigation", async ({ page }) => {
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  // Click "Спот" nav link
  const nav = page.getByRole("navigation", { name: "Primary" });
  await nav.getByRole("link", { name: "Спот" }).click();
  await page.waitForURL(`${BASE}/spot`);
  await waitForStableUI(page);

  // Active link has .is-active class — verify visually
  const activeLink = nav.locator(".app-shell__nav-link.is-active");
  await expect(activeLink).toHaveText("Спот");

  // Region snapshot of sidebar nav to verify active state styling
  await expect(nav).toHaveScreenshot("sidebar-nav-spot-active.png");
});
