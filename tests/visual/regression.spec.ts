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

// ── Stable fixtures for pages with backend-state-sensitive content ─────────────

// models: latest_run_scope/status appear in unmasked status-caption elements.
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

// runtime: card DL timestamps (last_heartbeat_at) change height when state changes.
// Path /runtime-status differs from SPA route /runtime — no port-specific regex needed.
const RUNTIME_OFFLINE_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  runtimes: [
    {
      runtime_id: "spot", label: "Spot Runtime", state: "offline",
      pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
      last_error: null, last_error_at: null,
      status_reason: "no matching runtime process detected", source_mode: "fixture",
    },
    {
      runtime_id: "futures", label: "Futures Runtime", state: "offline",
      pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
      last_error: null, last_error_at: null,
      status_reason: "no matching runtime process detected", source_mode: "fixture",
    },
  ],
};

// telegram: connectivity_detail text length changes after a real check is run,
// causing masked-rectangle height shifts in surrounding layout.
// Port-specific regex required: SPA route /telegram matches the same path.
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

// settings: env key presence depends on .env file state — must be stable across environments.
// Port-specific regex required: SPA route /settings matches the same path.
const SETTINGS_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "unknown",
  env_file_path: null,
  env_file_exists: false,
  fields: [
    { key: "BYBIT_API_KEY",           label: "Bybit Demo API Key",       value: "", masked: true,  present: false },
    { key: "BYBIT_API_SECRET",        label: "Bybit Demo API Secret",    value: "", masked: true,  present: false },
    { key: "BYBIT_MAINNET_API_KEY",   label: "Bybit MainNet API Key",    value: "", masked: true,  present: false },
    { key: "BYBIT_MAINNET_API_SECRET",label: "Bybit MainNet API Secret", value: "", masked: true,  present: false },
    { key: "TELEGRAM_BOT_TOKEN",      label: "Telegram Bot Token",       value: "", masked: true,  present: false },
    { key: "TELEGRAM_CHAT_ID",        label: "Telegram Chat ID",         value: "", masked: false, present: false },
    { key: "DB_URL",                  label: "Database URL",             value: "", masked: false, present: false },
  ],
};

// ── Snapshot pages ────────────────────────────────────────────────────────────
//
// Added routes and rationale:
//   runtime  — complex multi-card state machine layout; region baselines cover cards
//              individually but not inter-card spacing, page heading, button row.
//              Mocked so DL timestamps are stable (null → "n/a").
//   telegram — multi-section page (summary + connectivity panel + 3 history tables);
//              region baseline covers only the summary grid. Full-page catches
//              section-level layout regressions. Mocked for stable note text.
//   settings — configuration form with 7 labelled fields; entirely static once mocked;
//              lowest noise of all missing routes.
//
// Not added: logs (live log data, extensive masking needed), diagnostics (lower priority),
//            market/orderbook (live price data, very noisy), backtest (semi-dynamic results).

const SNAPSHOT_PAGES = [
  { name: "health",    url: "/" },
  { name: "spot",      url: "/spot" },
  { name: "futures",   url: "/futures" },
  { name: "analytics", url: "/analytics" },
  { name: "models",    url: "/models" },
  { name: "jobs",      url: "/jobs" },
  { name: "runtime",   url: "/runtime" },
  { name: "telegram",  url: "/telegram" },
  { name: "settings",  url: "/settings" },
];

for (const { name, url } of SNAPSHOT_PAGES) {
  test(`visual: ${name} — pixel regression`, async ({ page }) => {
    if (name === "models") {
      await injectMockResponse(page, "**/models", MODELS_FIXTURE);
    } else if (name === "runtime") {
      await injectMockResponse(page, "**/runtime-status", RUNTIME_OFFLINE_FIXTURE);
    } else if (name === "telegram") {
      await injectMockResponse(page, /127\.0\.0\.1:8765\/telegram$/, TELEGRAM_FIXTURE);
    } else if (name === "settings") {
      await injectMockResponse(page, /127\.0\.0\.1:8765\/settings$/, SETTINGS_FIXTURE);
    }

    await page.goto(`${BASE}${url}`);
    await waitForStableUI(page);

    await expect(page).toHaveScreenshot(`${name}.png`, {
      mask: getDynamicMasks(page),
      fullPage: true,
    });
  });
}
