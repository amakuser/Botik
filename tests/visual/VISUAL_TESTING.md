# Visual Testing Architecture

> Rules for extending and maintaining the visual verification layer.
> Read this before adding new visual tests or updating baselines.

## Layer Map

| Suite | File | Type | Baselines needed | When it detects issues |
|-------|------|------|-----------------|----------------------|
| Layout integrity | `layout.spec.ts` | JS geometry | No | After any CSS or layout change |
| Text clipping | `text-clip.spec.ts` | JS text check | No | After label/button/nav text or sizing changes |
| Full-page regression | `regression.spec.ts` | Pixel diff | Yes (6 pages) | After full-page visual change |
| Region/component | `regions.spec.ts` | Pixel diff | Yes (8 regions) | After component-level visual change |
| State-specific | `states.spec.ts` | Structural + Pixel diff | Yes (4 states) | After error/empty/loading/state UI changes |
| Interaction-aware | `interaction.spec.ts` | Structural + Pixel diff | Yes (4 results) | After action-triggered UI changes |

All suites run via: `.\scripts\test-visual.ps1`

## When to Add a Test

### Add a full-page regression baseline (`regression.spec.ts`)
- New route is added to the router
- An existing route has significant full-page layout changes
- Max 10–12 total (more = slow, noisy)

### Add a region baseline (`regions.spec.ts`)
- A new reusable component is added (card, panel, toolbar)
- An existing component changes structure (not just data values)
- When a component is too important to trust full-page masking
- Do NOT add a region for every new component — only components that:
  1. Appear on high-traffic pages
  2. Have non-trivial layout or visual structure
  3. Would break silently (no structural assertion catches it)

### Add an interaction-driven test (`interaction.spec.ts`)
- A button click produces a visible UI state change (result panel, error banner, status badge)
- A navigation action causes a visible sidebar or heading change
- A form submission changes visible page content
- Do NOT use for invisible/background state changes (API calls with no visible result)

### Add a state test (`states.spec.ts`)
- A new UI state is added that differs from the fixture "normal" state (empty, error, loading, running)
- When a new endpoint failure path produces a visible banner or message
- The state must be injectable via `page.route()` or already the fixture default

### Add a text-clip check (`text-clip.spec.ts`)
- After adding a new label, button label, or badge with constrained width
- After resizing the sidebar or changing nav label text

### Add a layout check (`layout.spec.ts`)
- Never add per-component — already covers all 14 routes globally
- Only extend if new structural element types need coverage beyond `main/section/table/.app-route`

## Fragile Baseline Rule

**If a baseline fails after a backend restart or data change, do NOT regenerate it.**

That is a symptom of live-backend dependency, not a legitimate baseline update. The fix is:
1. Inject a stable fixture via `injectMockResponse()` before `page.goto()`
2. Regenerate the baseline once against the fixed fixture
3. The test is now deterministic and immune to backend state

**Examples of fragile baselines fixed this way:**
- RuntimeStatusCard offline: `last_heartbeat_at` → null/timestamp swaps DL row height
- Telegram summary grid: `connectivity_detail` wraps to 2 lines after connectivity check → masked rectangle height shifts surrounding layout
- Models regression: `latest_run_scope/status` in `status-caption` changes when a job has run

**Rule:** masked area HEIGHT is still part of the screenshot. A masked rectangle sized by 2-line text differs from one sized by 1-line text even though the content is black. When note/description text wraps differently depending on backend state, mocking is required — masking alone is insufficient.

## When to Update Baselines

**Correct approach:** run `.\scripts\update-visual-baselines.ps1`, review the diff visually, then commit.

**Update baselines when:**
- An intentional UI change (color, spacing, typography, component structure) is reviewed and approved
- A new feature adds visible content to an existing page
- A dependency upgrade changes rendering (e.g., Framer Motion, Tailwind version)

**Do NOT update baselines when:**
- Tests fail due to dynamic data escaping the mask (fix the mask or add `injectMockResponse`)
- Tests fail due to timing (fix `waitForStableUI` timeout instead)
- Tests fail due to real visual regression (fix the regression)
- Tests fail after backend restart when no UI change occurred (add mock fixture instead)

## Masking Rules

**Mask dynamic values, not structural elements.**

- Prices, timestamps, PID numbers, latency values → always mask
- State labels (RUNNING/OFFLINE) → mask only if not the subject of the test
- Card headings, button labels, static descriptions → never mask (these are what we're protecting)

Bad mask (too broad, hides structure):
```typescript
mask: [page.locator("table tbody")] // hides entire table body
```

Good mask (targets only the value):
```typescript
mask: [page.locator("table tbody td:nth-child(2)")] // only the price column
```

## Network Interception Patterns

See `helpers.ts` for `injectBackendError` and `injectMockResponse`.

**WARNING:** `page.route("**/telegram", ...)` also matches `http://127.0.0.1:4173/telegram`
(the SPA route), breaking page load. Always use port-specific patterns when the route path
matches a frontend URL:

```typescript
// Wrong — intercepts SPA navigation too:
await injectBackendError(page, "**/telegram");

// Correct — targets only the backend port:
await injectBackendError(page, /127\.0\.0\.1:8765\/telegram$/);
```

Use `**/endpoint-name` only when the API path differs from any frontend route.

## Baseline File Naming

| Suite | Pattern | Example |
|-------|---------|---------|
| regression | `{page-name}.png` | `health.png` |
| regions | `region-{component}-{state}.png` | `region-runtime-spot-offline.png` |
| states | `state-{surface}-{state}.png` | `state-runtime-error-banner.png` |
| interaction | `{surface}-{action}-{result}.png` | `telegram-check-result.png` |

All baselines live in `tests/visual/baselines/` and are committed to git.
Baselines are platform-independent (generated by headless Chromium, fixed viewport 1280×800).

## Execution

```powershell
# All visual tests
.\scripts\test-visual.ps1

# Layout + text-clip only (no baselines, fastest)
.\scripts\test-visual.ps1 -Layout

# Pixel regression only
.\scripts\test-visual.ps1 -Regression

# After intentional UI change
.\scripts\update-visual-baselines.ps1
# then: git add tests/visual/baselines/ && git commit -m "chore: update visual baselines"
```

## Current Coverage State

### Routes with full-page baseline
health, spot, futures, analytics, models, jobs

### Routes with layout check only (no pixel baseline)
logs, runtime, telegram, diagnostics, settings, market, orderbook, backtest

### Components with region baseline
- RuntimeStatusCard (spot + futures, offline state)
- RuntimeStatusCard (spot, running state — mocked)
- DataBackfillJobCard
- DataIntegrityJobCard
- Health metrics grid
- Health pipeline section
- Telegram summary grid

### States covered
- Jobs history empty (fixture default)
- Runtime error (GET 500)
- Telegram error (GET 500)
- Health pipeline running (mocked runtime-status)
- Loading text (health.status = "загрузка" before data arrives)

### Interactions covered
- Telegram connectivity check → result panel (real API)
- Jobs start failure → action error banner (mocked POST)
- Runtime start → running state (fully mocked before/after)
- Sidebar nav click → active link styling

## What Is Still Not Covered

- Overlapping elements (z-index collisions) — no overlap detection
- Vertical overflow within correctly-sized containers
- Clipped text INSIDE a properly sized container (only overflow/ellipsis at container level)
- Generic div/span text clipping (only h1-h3, button, a, .status-chip, .surface-badge, .app-shell__nav-link)
- Hover/focus/keyboard states
- Cross-browser rendering differences (Chromium only)
- Responsive breakpoints below 1280px
- Transient loading spinners (too fast for reliable capture)
- Native Tauri window chrome (OS-rendered, not DOM)
- Semantic correctness (wrong label text that is readable but wrong)
- Desktop titlebar region (requires `VITE_BOTIK_DESKTOP=true`, skipped in standard suite)
- Routes without full-page baseline (8 routes: layout checks only)
