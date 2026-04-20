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
 *
 * Vision loop (OLLAMA_VISION=1):
 *   Extends DOM-level assertions with gemma3:4b region analysis.
 *   ACTION → SNAPSHOT (region) → ANALYSIS → DECISION
 *   Disabled by default; enabling adds ~1.5s per vision check.
 */

import { expect, test } from "@playwright/test";
import { injectBackendError, injectMockResponse, waitForStableUI } from "./helpers";
import {
  buildCrossCheck,
  captureRegion,
  classifyElementState,
  compareStates,
  detectActionBanner,
  detectPanelVisibility,
  isOllamaVisionEnabled,
  logVisionResult,
} from "./vision_loop.helpers";

const BASE = "http://127.0.0.1:4173";

// ── Telegram: check button → result panel ─────────────────────────────────────

// Fixed telegram snapshot for GET /telegram (prevents SPA route collision and live-data dependency).
const TELEGRAM_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "fixture",
  summary: {
    bot_profile: "default",
    token_profile_name: "TELEGRAM_BOT_TOKEN",
    token_configured: false,
    internal_bot_disabled: false,
    connectivity_state: "unknown",
    connectivity_detail: "Проверка не выполнялась.",
    allowed_chat_count: 0,
    allowed_chats_masked: [],
    commands_count: 0,
    alerts_count: 0,
    errors_count: 0,
    last_successful_send: null,
    last_error: null,
    startup_status: "unknown",
  },
  recent_commands: [],
  recent_alerts: [],
  recent_errors: [],
  truncated: { recent_commands: false, recent_alerts: false, recent_errors: false },
};

// Fixed connectivity check response — deterministic state label in the result panel.
const CONNECTIVITY_CHECK_RESULT = {
  checked_at: "2026-01-01T00:00:00Z",
  source_mode: "fixture",
  state: "healthy",
  detail: "getMe succeeded — bot is reachable.",
  bot_username: "test_bot",
  latency_ms: 42,
  error: null,
};

test("interaction: telegram check → result panel appears with state label", async ({ page }) => {
  // Mock GET /telegram — port-specific to avoid intercepting the SPA navigation at 4173/telegram.
  // Also prevents live state from the previous connectivity check polluting the page.
  await injectMockResponse(page, /127\.0\.0\.1:8765\/telegram$/, TELEGRAM_FIXTURE);

  // Mock POST /telegram/connectivity-check — makes the check result deterministic.
  // Path has no SPA collision, so simple glob is safe.
  await injectMockResponse(page, "**/telegram/connectivity-check", CONNECTIVITY_CHECK_RESULT);

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
  await expect(result.locator("strong")).toHaveText("healthy");

  // Region snapshot — mask only the meta badges (bot username, latency, source mode)
  await expect(result).toHaveScreenshot("telegram-check-result.png", {
    mask: [page.locator(".telegram-check-result__meta")],
  });

  // ── Vision loop: confirm result panel is visually present and shows "healthy" ──
  if (isOllamaVisionEnabled()) {
    const panelImg = await captureRegion(result);
    const { result: vision, analysis, confidence } = await detectPanelVisibility(panelImg, "telegram.check.result@after");

    // DOM cross-check: Playwright confirms element is visible at the locator level
    const isDomVisible = await result.isVisible();
    const crossCheck = buildCrossCheck(
      vision.panel_visible ? "visible" : "hidden",
      isDomVisible ? "visible" : "hidden",
    );

    logVisionResult(
      "telegram-check@after",
      analysis,
      vision.panel_visible ? `panel_visible=true label=${vision.primary_label ?? "?"}` : "panel_visible=false",
      confidence,
      crossCheck,
    );

    expect(vision.panel_visible, "[vision] result panel should be visible after check").toBe(true);
    expect(
      crossCheck.outcome,
      `[vision+DOM] telegram panel: vision=${crossCheck.vision_value} dom=${crossCheck.dom_value}`,
    ).not.toBe("conflict");

    if (vision.primary_label !== null) {
      expect(
        vision.primary_label.toLowerCase(),
        "[vision] primary label should contain 'healthy'",
      ).toContain("healthy");
    }
  }
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

  // ── Vision loop: confirm the error banner is visually present ──────────────
  if (isOllamaVisionEnabled()) {
    const errorEl = page.getByTestId("jobs.action-error");
    const bannerImg = await captureRegion(errorEl);
    const { result: vision, analysis, confidence } = await detectActionBanner(bannerImg, "jobs.action-error@after");

    // DOM cross-check: the error element is visible per Playwright locator
    const isDomBannerVisible = await errorEl.isVisible();
    const crossCheck = buildCrossCheck(
      vision.has_action_banner ? "visible" : "hidden",
      isDomBannerVisible ? "visible" : "hidden",
    );

    logVisionResult(
      "jobs-start-fail@after",
      analysis,
      vision.has_action_banner
        ? `has_banner=true type=${vision.banner_type ?? "?"} text=${(vision.text ?? "").slice(0, 60)}`
        : "has_banner=false",
      confidence,
      crossCheck,
    );

    if (confidence >= 0.5) {
      expect(vision.has_action_banner, "[vision] action error banner should be visible after failed start").toBe(true);
      expect(
        crossCheck.outcome,
        `[vision+DOM] jobs error banner: vision=${crossCheck.vision_value} dom=${crossCheck.dom_value}`,
      ).not.toBe("conflict");
    } else {
      console.log(`[vision] jobs banner confidence=${confidence.toFixed(2)} — skipping vision assertion (model uncertain), DOM confirmed visible`);
    }
  }
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

  const spotCard = page.getByTestId("runtime.card.spot");

  // ── Vision loop: capture BEFORE state ─────────────────────────────────────
  let stateBefore: import("./vision_loop.helpers").StateClassification | null = null;

  if (isOllamaVisionEnabled()) {
    const cardBeforeImg = await captureRegion(spotCard);
    const { result, analysis } = await classifyElementState(cardBeforeImg, "runtime.card.spot@before");
    stateBefore = result;
    logVisionResult(
      "runtime-start@before",
      analysis,
      `badge=${result.badge} color=${result.color}`,
    );
  }

  // Action
  await page.getByTestId("runtime.start.spot").click();

  // After: state indicator shows RUNNING, stop button enabled
  await expect(page.getByTestId("runtime.state.spot")).toHaveText("RUNNING", { timeout: 5_000 });
  await expect(page.getByTestId("runtime.stop.spot")).toBeEnabled();

  // Region snapshot of the spot card in running state — mask dynamic timestamp/PID fields
  await expect(spotCard).toHaveScreenshot("runtime-card-running-state.png", {
    mask: [
      page.getByTestId("runtime.heartbeat.spot"),
      page.getByTestId("runtime.pids.spot"),
      spotCard.locator("dl dd"),  // timestamps in details
    ],
  });

  // ── Vision loop: capture AFTER state and confirm transition ──────────────
  if (isOllamaVisionEnabled()) {
    const cardAfterImg = await captureRegion(spotCard);
    const { result: stateAfter, analysis, confidence: confAfter } = await classifyElementState(
      cardAfterImg, "runtime.card.spot@after",
    );

    // DOM cross-check: Playwright DOM text matches vision badge
    const domText = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();
    const crossCheck = buildCrossCheck(stateAfter.badge, domText);

    logVisionResult(
      "runtime-start@after",
      analysis,
      `badge=${stateAfter.badge} color=${stateAfter.color}`,
      confAfter,
    );

    logVisionResult(
      "runtime-start@cross-check",
      analysis,
      `cross_check=${crossCheck.outcome}`,
      confAfter,
      crossCheck,
    );

    expect(
      crossCheck.outcome,
      `[vision+DOM] runtime state: vision=${crossCheck.vision_value} dom=${crossCheck.dom_value}`,
    ).not.toBe("conflict");

    if (stateBefore !== null) {
      const comparison = compareStates(stateBefore, stateAfter, { from: "OFFLINE", to: "RUNNING" });
      logVisionResult(
        "runtime-start@compare",
        analysis,
        `transition=${comparison.decision} from=${comparison.from_badge} to=${comparison.to_badge}`,
      );
      expect(
        comparison.decision,
        `[vision] expected OFFLINE→RUNNING transition, got ${comparison.from_badge}→${comparison.to_badge}`,
      ).toBe("transition_confirmed");
    } else {
      expect(stateAfter.badge, "[vision] card should show RUNNING after start action").toBe("RUNNING");
    }
  }
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
