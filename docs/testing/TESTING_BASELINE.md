# Testing Baseline — Botik

> Active test stack as of 2026-04-26 (post M1 cleanup).
> Do not mark anything as "working" without a recorded test run.

## Truth status — at a glance

| Layer                                              | Status               | Data source                                       | Confidence |
|----------------------------------------------------|----------------------|----------------------------------------------------|------------|
| Unit tests (`pytest`)                              | production-grade     | real code                                          | high       |
| Layout integrity (`tests/visual/layout.spec.ts`)   | production-grade     | JS geometry, no fixtures                           | high       |
| Text clipping (`tests/visual/text-clip.spec.ts`)   | production-grade     | JS text check, no fixtures                         | high       |
| Pixel regression (`tests/visual/regression.spec.ts`) | production-grade   | mocked fixtures + committed baselines              | high       |
| Region/component pixel (`tests/visual/regions.spec.ts`) | production-grade | mocked fixtures + committed baselines              | high       |
| State-specific (`tests/visual/states.spec.ts`)     | production-grade     | mocked fixtures + injected error states            | high       |
| Semantic auto-region (`tests/visual/semantic.spec.ts` + helpers) | production-grade | real backend, no mocks               | high       |
| Heuristic / Claude vision (`tests/vision/vision.spec.ts`) | production-grade | screenshots + heuristic OR Claude API         | high       |
| Desktop-smoke (`tests/desktop-smoke/`)             | browser-only         | real backend + real Vite + headless Chromium (NOT the Tauri window) | high for the web layer only |

The Tauri desktop window itself is not currently covered by an automated test lane — `scripts/run-primary-desktop.ps1` is the manual smoke.

---

## A. Unit Tests

- **Runner:** `pytest`
- **Layout:** `tests/unit/python/` (deterministic, hermetic) plus integration specs at top level of `tests/`.
- **Active count:** 255 tests collected (run `python -m pytest tests/ --collect-only -q | tail -1`).
- **Fast subset for green-light:** `python -m pytest tests/unit/python/` (22 tests, ~1.3s).
- **Fixtures:** `tests/fixtures/` — JSON / YAML feeders for read-services (runtime status, telegram, models). Created via `tests/fixtures/create_fixtures.py`.

## B. Visual / Frontend Tests

All under `tests/visual/`, run via Playwright. Config: `playwright.visual.config.ts`.

- **Layout integrity (`layout.spec.ts`):** JS geometry — horizontal overflow, zero-height containers, left-edge clipping. Runs on every page in the app shell. No baselines.
- **Text clipping (`text-clip.spec.ts`):** detects `overflow: hidden` truncation on labels, buttons, badges. JS-based, no baselines.
- **Pixel regression (`regression.spec.ts`):** 6 high-value pages compared against committed baselines in `tests/visual/baselines/*.png`. Update via `scripts/update-visual-baselines.ps1` after intentional UI change.
- **Region/component (`regions.spec.ts`):** component-level pixel snapshots for high-value cards/panels.
- **State-specific (`states.spec.ts`):** fixture-injected error/empty/running states.
- **Semantic auto-region (`semantic.spec.ts` + `semantic.helpers.ts`):** discovery walks `[data-ui-role]`. Asserts contract holds (roles present, keys stable, recommended_check sane). Independent of pixel diff — survives label/CSS changes.

Baselines and fixtures are the only data sources. No live trading, no Bybit calls.

Update visual baselines:
```
pwsh ./scripts/update-visual-baselines.ps1
```

## C. Vision Tests (`tests/vision/`)

- **`vision.spec.ts`:** screenshots each page and runs semantic quality analysis.
  - `VISION_MODE=llm` — sends to Claude API (requires `ANTHROPIC_API_KEY`)
  - `VISION_MODE=heuristic` — JS-based checks (text size, contrast, overlap, empty panels)
  - Auto-selects `llm` if `ANTHROPIC_API_KEY` set, else `heuristic`.
  - Strict mode (`VISION_STRICT=1`, default): fails on `severity=high AND confidence>0.7`.
  - Report mode (`VISION_STRICT=0`): never fails, writes `.artifacts/local/latest/vision/report.json`.
- **Config:** `tests/vision/playwright.vision.config.ts`.
- **Helpers:** `vision.helpers.ts`, `vision.prompts.ts`, `vision.config.ts`.

The local-Ollama / gemma3:4b research stack (vision_discover, vision_diff, vision_interpret, semantic_gap, agent_audit, auto_test_gen, live-backend, interaction, region-guardrail) was retired in M1 cleanup 2026-04-26. The remaining `vision.spec.ts` is the focused product-grade vision review.

## D. Desktop Smoke (`tests/desktop-smoke/`)

Browser-only headless smoke against the real Vite preview + the real app-service. Does NOT open the Tauri desktop window.

```
pwsh ./scripts/test-desktop-smoke.ps1
pwsh ./scripts/visual-audit.ps1   # wrapper that opens the html report afterwards
```

## E. Manual smoke for Tauri desktop

There is no automated test for the actual Tauri OS window today. Manual procedure:

```
pwsh ./scripts/run-primary-desktop.ps1
```

The script kills stale 8765 listeners, ensures Vite, spawns the app-service sidecar, and launches `apps/desktop/src-tauri/target/release/botik_desktop.exe`. Operator visually verifies pages render and routes work.

---

## What was retired in M1 cleanup (2026-04-26)

- `tests/visual/interaction.spec.ts` — vision-anchored, skipped without `OLLAMA_VISION=1`.
- `tests/visual/live-backend.spec.ts` — vision-anchored, 1202 lines, skipped without `OLLAMA_VISION=1`.
- `tests/visual/region-guardrail.spec.ts` — proved internal classifier behavior, infrastructure-only.
- `tests/visual/vision_loop.helpers.ts` and untracked `vision_diff/discover/interpret`, `semantic_gap`, `auto_test_gen`, `auto-test-gen.spec.ts`, `semantic-gap.spec.ts`, `vision_diff.spec.ts`, `vision_interpret.spec.ts`.
- `tests/vision/agent_audit.spec.ts` — exploratory LLM-judge.
- `tests/desktop-native/` — used the deleted PyInstaller `botik_desktop.exe`. The Tauri-built exe at `apps/desktop/src-tauri/target/release/botik_desktop.exe` does not currently have an automated native test.
- `tests/test_strategy.py` — exercised the retired root `/strategies` stack.
- `tests/test_rule_engine.py` — exercised the retired `/stats` stack.
- `docs/testing/EXPERIMENTAL_VISION_TRACK.md`, `docs/testing/NEXT_STEPS.md` — vision research history and roadmap.

External backup of the retired source: `C:/ai/aiBotik_legacy_backup_2026-04-26/` (24 files, MOVED_FILES.md).

---

## Commands

```bash
# Unit tests (full suite)
python -m pytest tests/

# Unit tests (fast subset)
python -m pytest tests/unit/python/

# Frontend type-check
cd frontend && npx tsc --noEmit

# Visual suite (mocked fixtures, baselines)
npx playwright test --config tests/visual/playwright.visual.config.ts

# Vision suite
npx playwright test --config tests/vision/playwright.vision.config.ts
ANTHROPIC_API_KEY=... VISION_MODE=llm npx playwright test --config tests/vision/playwright.vision.config.ts

# Desktop browser smoke
pwsh ./scripts/test-desktop-smoke.ps1

# Manual Tauri desktop smoke
pwsh ./scripts/run-primary-desktop.ps1
```
