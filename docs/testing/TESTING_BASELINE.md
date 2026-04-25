# Testing Baseline — Botik

> Verified as of 2026-04-25. Do not mark anything as "working" without a recorded test run.

## Truth status — at a glance

| Layer                                              | Status               | Data source                                       | Confidence |
|----------------------------------------------------|----------------------|----------------------------------------------------|------------|
| Unit tests (`pytest`)                              | production-grade     | real code                                          | high       |
| Visual pixel regression (`tests/visual/`)          | production-grade     | mocked fixtures                                    | high       |
| Interaction vision loop (`interaction.spec`)       | production-grade     | mocked fixtures                                    | high       |
| Live backend vision (`live-backend.spec`)          | production-grade     | real backend (browser webview)                     | high       |
| Semantic auto-region (`semantic.spec` + helpers)   | production-grade     | real backend, no mocks                             | high       |
| Exploratory agent audit (`agent_audit.spec`)       | partial — report only | mocked fixtures                                   | medium     |
| Claude API vision (`tests/vision/vision.spec`)     | production-grade     | mocked fixtures                                    | high       |
| **Desktop-smoke** (`tests/desktop-smoke/`)         | **browser-only**     | real backend + real Vite + headless Chromium (NOT the Tauri window) | high for the web layer only |
| **Desktop-native shell** (`tests/desktop-native/*.ps1`) | **production-grade** | **real `botik_desktop.exe` + real sidecar + Win32 API** | **high** |
| **Desktop-native interactive** (`tests/desktop-native/interactive/`) | **production-grade** | **real desktop exe + WebView2 CDP attach + reusable framework** | **high** |

Two distinctions worth keeping in mind:
- "Live backend vision" validates the web layer (headless Chromium against a real uvicorn). It does NOT open the Tauri desktop window.
- "Desktop-native shell" launches the real `botik_desktop.exe` and drives the OS window via `user32.dll` — no Playwright, no browser, no localhost:4173 DOM assertions. This is the only lane that proves the desktop shell chrome and sidecar lifecycle work outside a browser.

---

## A. STABLE / VERIFIED SYSTEM

### 1. Unit Tests
- **Status:** verified
- **Runner:** `pytest`
- **Count:** ~350+ tests (as of v0.0.65)
- **Location:** `tests/`
- **Command:** `pytest`
- **Last verified:** 2026-04-20 (all pass)

### 2. Visual Regression Tests
- **Status:** verified
- **Framework:** Playwright + pixelmatch
- **Location:** `tests/visual/`
- **Config:** `playwright.config.ts`
- **Layers:**
  - `regions.spec.ts` — component-level pixel regression with mocking
  - `regression.spec.ts` — full-page pixel regression with mocking
  - `interaction.spec.ts` — click/navigate interaction stability
- **Mocking rules:** All API calls intercepted via `page.route()` before `page.goto()` to prevent dynamic-data flicker
- **Baselines:** `tests/visual/baselines/` — committed PNG snapshots
- **Command:** `npx playwright test tests/visual/`
- **Test count:** 48 tests (last verified passing)
- **Known fragile areas:**
  - `last_heartbeat_at` causes height change in runtime card — mocked with `OFFLINE_RUNTIME_FIXTURE`
  - `connectivity_detail` text length varies — mocked with `TELEGRAM_FIXTURE`
  - model status caption — mocked with `MODELS_FIXTURE`

### 3. Vision Layer (screenshot semantic review)
- **Status:** verified (experimental wrapper, but underlying API is stable)
- **Framework:** Playwright + Anthropic Claude API
- **Location:** `tests/vision/`
- **Config:** `tests/vision/playwright.vision.config.ts`
- **Files:**
  - `vision.config.ts` — page list, STRICT mode flags
  - `vision.helpers.ts` — screenshot capture + Claude API call
  - `vision.prompts.ts` — structured JSON prompt
  - `vision.spec.ts` — 9 pages tested
- **Model used:** Claude API (not local Ollama)
- **Requires:** `ANTHROPIC_API_KEY` in environment
- **STRICT mode:** enabled — false positives filtered (gradient contrast excluded)
- **Command:** `npx playwright test --config tests/vision/playwright.vision.config.ts`
- **Last verified:** 9/9 pages pass, 0 false positives

### 3a. Local Vision Loop (gemma3:4b — Ollama)
- **Status:** production-grade
- **Framework:** Playwright + Ollama gemma3:4b (local)
- **Location:** `tests/visual/vision_loop.helpers.ts`
- **Activation:** `OLLAMA_VISION=1` (disabled by default — CI-safe)
- **Key features:**
  - JSON schema validation + confidence field
  - Retry on empty/unparseable response (max 2 attempts, bypassCache=true)
  - In-memory region cache (FNV-32 hash key)
  - DOM cross-check (confirmed/conflict/uncertain)
  - Structured logging per vision event
- **Classifiers (all proven 100% reliable 3/3 iter — `scripts/probe_vision_signals.mjs` 2026-04-21):**
  - `classifyElementState` — status badge (RUNNING/OFFLINE/UNKNOWN)
  - `detectErrorText` — error/failure text in a panel (replaced the fragile "action banner" path on bare `<p>` crops)
  - `detectActionBanner` — standalone action notification with chrome
  - `detectPanelVisibility` — result panel visible/hidden + primary_label
- **Known NOT reliable:** `active_nav_styling` (0/3 iter — a 4B model cannot read subtle `.is-active` CSS)
- **Model:** gemma3:4b (1.4s warm, 100% JSON valid, GPU only)
- **Requires:** Ollama running at 127.0.0.1:11434 with gemma3:4b loaded
- **Minimum region size for reliable analysis:** `VISION_REGION_MIN` in `tests/visual/helpers.ts` — width ≥ 120 px, height ≥ 60 px, font ≥ 12 px. Use `measureRegion()` + `isRegionVisionReady()` before calling the vision helpers on small crops.

### 3b. Live Backend Vision (`tests/visual/live-backend.spec.ts`)
- **Status:** production-grade
- **Activation:** `OLLAMA_VISION=1` + real backend at `127.0.0.1:8765` + frontend at `127.0.0.1:4173`
- **Scope:** two read-only scenarios with NO `page.route` mocking:
  - `live: health` — frontend calls real `/health`, vision reads the intro panel, cross-check against the backend response (100% confirmed)
  - `live: runtime` — frontend calls real `/runtime-status`, vision reads both `runtime.card.*` crops, cross-check of vision↔DOM↔backend state (100% confirmed)
- **What is validated against the real backend:** health status string, service name, version string; runtime_id and state for each runtime. DOM-vs-backend assertion is hard (fails the test if they diverge).
- **What remains mocked (fixture-only) elsewhere:**
  - `regression.spec.ts`, `regions.spec.ts`, `states.spec.ts` — full-page pixel diff with mocked fixtures (intentional — pixels must be reproducible)
  - `interaction.spec.ts` — user-action paths (telegram check, jobs start-fail, runtime start) mock both the list fetch and the action endpoint so the test stays deterministic
  - `tests/vision/vision.spec.ts` — Claude API pass uses mocked fixtures for the same reason
- **Startup:** `.\scripts\dev-app-service.ps1` (backend) + `.\scripts\dev-frontend.ps1` (frontend) + Ollama serve + `gemma3:4b` loaded.

### 3bb. Semantic Auto-Region System (`tests/visual/semantic.helpers.ts` + `semantic.spec.ts`)
- **Status:** production-grade
- **Goal:** stop hard-coding region selectors and expected text in tests. Frontend tags meaningful elements with `data-ui-*` attributes (parallel contract to `data-testid`, NOT a replacement); helpers discover, snapshot and diff those regions.
- **Contract emitted by frontend:**
  - `data-ui-role` — what the element IS (`runtime-card`, `status-badge`, `status-callout`, `runtime-action`, `action-row`, `page`, `jobs-history`, `jobs-list`, `jobs-list-item`, `empty-state`, `job-preset`, `job-status`, `job-toolbar`, `job-action`)
  - `data-ui-scope` — semantic owner (`spot`, `futures`, `jobs`, `data-backfill`, `data-integrity`, `selected`, `selected-job`, ...)
  - `data-ui-state` — current state (`offline|running|degraded|empty|populated|enabled|disabled` and per-feature values)
  - `data-ui-action` — `start|stop` on actionable elements
  - `data-ui-kind` — `info|warning|error` on callouts
- **API:**
  - `collectSemanticRegions(page)` — single `page.evaluate` walks `[data-ui-role]`, returns `SemanticRegion[]` with `{role, scope, state, action, kind, bbox, text_length, visible, disabled, recommended_check}`. No selector list hard-coded in tests.
  - `captureSemanticSnapshot(page)` — `{captured_at, regions[]}`.
  - `compareSemanticSnapshots(before, after)` — emits 6 change types: `state_changed`, `action_availability_changed`, `callout_changed`, `visibility_changed`, `region_added`, `region_removed`. Stable across text changes, language flips, bbox movement, viewport resize.
  - `recommendedCheck(role, bbox)` — pure mapping (role × size) → `vision | dom | backend | hybrid`. Buttons/containers always `dom`; badges/callouts `vision` if vision-ready; cards `hybrid`.
- **Where applied:**
  - `RuntimeStatusCard` (spot/futures runtime cards, badges, action buttons, callouts) — since 2026-04-25.
  - `JobMonitorPage`, `JobToolbar`, `DataBackfillJobCard`, `DataIntegrityJobCard`, `JobStatusCard` — since 2026-04-25.
- **Verified at runtime (2026-04-25):**
  - `semantic.spec.ts` 4/4: runtime contract, jobs contract, state-flip diff, action-availability flip.
  - `live-backend.spec.ts` jobs scenario logs `semantic_history_state=empty semantic_regions=15` against real backend.
  - `live-backend.spec.ts` 3 runtime interaction scenarios log `state_changed`, `action_availability_changed`, `callout_changed`, `region_added/removed` from a real start/stop transition.
- **Canonical state layer (2026-04-25):** state vocabulary is no longer string literals. Three enums in `semantic.helpers.ts` — `RUNTIME_STATE = {INACTIVE, ACTIVE, DEGRADED}`, `JOBS_STATE = {EMPTY, NON_EMPTY}`, `ACTION_STATE = {ENABLED, DISABLED}` — plus a `CANONICAL_MAP` mapping (role × raw `data-ui-state`) → canonical bucket. Every region carries both `state` (raw) and `canonical_state`. The diff compares `canonical_state` first (raw fallback only when both sides are unmapped). All test asserts go through the enum: `expect(card.canonical_state).toBe(RUNTIME_STATE.INACTIVE)`, never `expect(card.state).toBe("offline")`. A frontend rename like `offline → idle` surfaces as `canonical_state === null` and is caught by the dedicated `canonical state survives a UI rename` spec.
- **Honest limits:** contract still feature-by-feature (only runtime + jobs); 12 frontend pages still without `data-ui-*`; per-job lifecycle states (`queued`, `succeeded`, ...) on `jobs-list-item` and `selected-job` status badge are intentionally outside any canonical bucket — they would need a fourth enum (`JOB_LIFECYCLE_STATE`) before assertions can move off raw strings.

### 3c. Exploratory Agent Audit
- **Status:** partial — report-only, opt-in
- **Location:** `tests/vision/agent_audit.spec.ts`
- **Activation:** `OLLAMA_AGENT=1` (skips silently otherwise)
- **Output:** `.artifacts/local/latest/vision/agent-audit.json`
- **Risk buckets:** `matches_expected | unexpected | likely_broken | uncertain`
- **2026-04-21 update — expected-state awareness:**
  Each scanned region now carries an explicit `expected` description that is injected into the model prompt. Previously the audit flagged every OFFLINE runtime as `likely_broken` because a small model cannot distinguish "expected offline" from "unexpectedly broken" without context. After the change, the runtime page audit reports matches=4, unexpected=0, broken=0 — the honest baseline.
- **Honest scope limit:** this is a triage tool, not a UI audit. Any `unexpected` finding must graduate to a deterministic test in `tests/visual/interaction.spec.ts` before it can gate anything.
- **CI safe:** never calls `test.fail()` — report-only.

### 3d. Native Desktop Shell Lane (`tests/desktop-native/`)
- **Status:** production-grade
- **Two modes:**
  - `run-automated-smoke.ps1` -- fast, exit-coded, artifact-minimal
  - `run-visible-review.ps1` -- human-observed, 2s pauses, numbered per-step screenshots (full-screen + window-rect), optional MP4 via ffmpeg, leaves window open so the operator can interact after the run
- **What it exercises (all against a real HWND):**
  - Launch of `apps/desktop/src-tauri/target/release/botik_desktop.exe` + HWND appears within 60s
  - Window title is exactly `Botik` and the class is NOT `ConsoleWindowClass` (the console-subsystem exe also attaches a console host with a title that contains "botik" as substring -- disambiguation is required)
  - `GetWindowRect` returns plausible geometry (1280x~480-800 client area)
  - `SetWindowPos` moves the window to a new position within 20px of target
  - `ShowWindow(SW_MINIMIZE)` / `IsIconic`; `SW_RESTORE`; `SW_SHOWMAXIMIZED` / `IsZoomed`
  - The Tauri-managed uvicorn sidecar on 127.0.0.1:8765 responds to `GET /health` with `{status:ok, service:botik-app-service}` -- this proves the sidecar was really spawned by the exe, not by the test script
  - Webview client area has >=5 distinct sampled colours via `CopyFromScreen` over the window rect (PrintWindow returns black on WebView2 -- known platform limit, documented in the README)
  - `PostMessage(WM_CLOSE)` + wait for exit + port 8765 freed + relaunch + fresh HWND + fresh /health
- **Artifacts:** `.artifacts/local/latest/desktop-native/<mode>/{report.json, screenshots/, logs/, session.mp4?}`
- **Explicit non-goals:** no browser, no Playwright, no headless Chromium, no localhost:4173 DOM assertions. If you need web-layer tests use `tests/visual/*` or `tests/desktop-smoke/*`.
- **Limitations (documented in README):** interactive drag-from-title-bar is not simulated (programmatic `SetWindowPos` covers the OS side of that); multi-monitor captures are PrimaryScreen-only; the release exe bakes `devUrl=http://127.0.0.1:4173` and therefore still needs Vite on 4173 (the orchestrator starts it if missing).

### 3e. Native Desktop Interactive (`tests/desktop-native/interactive/`)
- **Status:** production-grade
- **Purpose:** a single reusable state-aware automation framework for every future interactive flow against the real desktop app. Scenarios import from `framework/index.ts`; they do not implement fresh automation logic per screen.
- **Approach:** `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9223` on the Tauri exe enables WebView2 CDP. Playwright `chromium.connectOverCDP()` attaches to the real webview. Every action (click, fill, scroll, screenshot, network capture) runs over CDP — no physical mouse, no keyboard, no focus stealing.
- **Framework primitives (`tests/desktop-native/interactive/framework/`):**
  - `harness.ts` — `DesktopHarness.launch()` kills stale 8765, ensures Vite, spawns `botik_desktop.exe`, attaches Playwright via CDP, enables Network domain; `detach()` cleans up only what it owns
  - `detect.ts` — `detectCurrentRoute`, `detectActiveTab`, `detectBlockingState` (modal/error/loader), `detectScrollContainers`, `detectElement`
  - `reconcile.ts` — `ensureRoute`, `ensureActiveTab`, `ensureElementVisible`, `waitForStableDom`, `recoverToRoute` (+ `ReconcileFailure` structured error)
  - `actions.ts` — `fillFieldByLabel`, `fillFieldByTestId`, `clickByRole`, `clickByText`, `scrollContainerTo`, `scrollDocumentBy` (all non-intrusive)
  - `verify.ts` — `waitForBackendCall` (wraps an action in `waitForResponse`), `waitForUiState`, `captureScreenshot`, `verifyVisibleText`
  - `evidence.ts` — `EvidenceRecorder` taps console + CDP `Network.*`; `captureEvidence` writes PNG + HTML + console log + network TSV per step; `classifyFailure` buckets thrown errors
- **Verified scenarios (first run 2026-04-21, all pass):**
  - `scenarios/settings-test-connection.spec.ts` — nav 3 tabs (/, /jobs, /runtime, /settings), fill 2 fields, click "Проверить подключение", capture POST /settings/test-bybit request body (verified contains `BOTIK_NATIVE_TEST_KEY`), verify ✓/✗ badge in UI, programmatically drift to /logs, `recoverToRoute("/settings")`, verify page title
  - `scenarios/non-intrusive-sentinel.spec.ts` — parks Notepad in foreground, runs framework primitives, asserts steady-state foreground HWND is NOT Botik (neither title "Botik" nor PID matches harness pid)
  - `scenarios/scroll-architecture-audit.spec.ts` — navigates every route, dumps doc + nested scroll containers into `scroll-report.json`
- **Silent launch:** the release exe is rebuilt with `#![cfg_attr(all(not(debug_assertions), target_os="windows"), windows_subsystem="windows")]` in `apps/desktop/src-tauri/src/main.rs`. No console host, no flash.

### 4. Dev Server & Screenshot API
- **Status:** verified
- **Tool:** BotikDevServer (`botik_tools/`)
- **Port:** localhost:9989
- **Endpoints:**
  - `GET /screenshot` — full-page PNG
  - `POST /navigate {"tab": "<page>"}` — tab switch
  - `GET /api/<method>` — API passthrough
  - `GET /rebuild-html` — rebuild from components
- **Used for:** manual visual audit without browser interaction
- **Script:** `python C:\ai\botik_tools\audit.py --screenshot`

### 5. Visual Test Script (PowerShell)
- **Status:** verified
- **File:** `scripts/test-vision.ps1`
- **Function:** runs vision layer tests with ANTHROPIC_API_KEY set

---

## B. KEY CONSTRAINTS

- Visual baselines must be regenerated when: UI structure changes, page layout changes, data schema changes
- NEVER update baselines without visual inspection of diff
- SPA single-page collision: if two tests share the same Playwright page object, navigation state may bleed across tests — each test gets its own `page` object
- Mocking must be injected BEFORE `page.goto()`, not after

---

## C. CI STATUS

- GitHub Actions: `.github/workflows/windows-package.yml`
- CI runs: build + package on push to master
- Visual tests: NOT currently in CI (require dev server running)
- Unit tests: included in CI pipeline

---

## D. TEST COMMANDS REFERENCE

```bash
# Unit tests
pytest

# Visual regression (requires dev server on :4173)
npx playwright test tests/visual/

# Visual regression with local vision loop (requires Ollama + gemma3:4b)
OLLAMA_VISION=1 npx playwright test tests/visual/interaction.spec.ts --config tests/visual/playwright.visual.config.ts

# Live backend vision (requires Ollama + gemma3:4b + real backend on :8765 + frontend on :4173)
OLLAMA_VISION=1 npx playwright test tests/visual/live-backend.spec.ts --config tests/visual/playwright.visual.config.ts

# Claude API vision layer (requires ANTHROPIC_API_KEY)
npx playwright test --config tests/vision/playwright.vision.config.ts

# Exploratory agent audit (requires Ollama + gemma3:4b)
OLLAMA_AGENT=1 npx playwright test tests/vision/agent_audit.spec.ts --config tests/vision/playwright.vision.config.ts

# Probe scripts (ad-hoc signal quality checks — not part of the test suite)
node scripts/probe_jobs_vision.mjs       # prompt/crop matrix on the jobs error scenario
node scripts/probe_vision_signals.mjs    # reliability of each signal type (3 iter each)

# Native desktop shell (real botik_desktop.exe + real Win32 window, NO browser)
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-automated-smoke.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-visible-review.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-visible-review.ps1 -TearDown

# Native desktop interactive (real desktop exe + WebView2 CDP + reusable framework)
npx playwright test --config tests/desktop-native/interactive/playwright.interactive.config.ts
npx playwright test --config tests/desktop-native/interactive/playwright.interactive.config.ts --grep "non-intrusive"
npx playwright test --config tests/desktop-native/interactive/playwright.interactive.config.ts --grep "scroll-architecture"

# Lint
ruff check .
```
