# Testing Baseline — Botik

> Verified as of 2026-04-20. Do not mark anything as "working" without a recorded test run.

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

# Visual regression (requires dev server on :9989)
npx playwright test tests/visual/

# Vision layer (requires ANTHROPIC_API_KEY)
npx playwright test --config tests/vision/playwright.vision.config.ts

# Lint
ruff check .
```
