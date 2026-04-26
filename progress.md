# Botik — Текущее состояние проекта

> Обновлять перед каждым значимым шагом (правило #4 в CLAUDE.md).
> Последнее обновление: 2026-04-26

---

## Стек

- **Backend:** Python 3.11, pybit (Bybit API), SQLite (основная) + PostgreSQL (через DB_URL)
- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 + Framer Motion
- **Desktop shell:** Tauri 2 (Rust) — единственный поддерживаемый GUI/product path
- **ML:** scikit-learn / PyTorch, pandas / numpy
- **Infra:** GitHub Actions CI, Tauri desktop build, PostgreSQL 18 (windows direct)

---

## Статус по зонам

### GUI — React/Tauri Frontend

**Путь:** `C:\ai\aiBotik\frontend\`  
**Статус:** ✅ Работает (14 страниц)  
**CSS:** Кастомный app.css (2000+ строк, BEM), тёмная тема, warm accent (#d7cbb1)  
**UI-Foundation:** ✅ Tailwind v4 + shadcn/ui primitives (Button, Badge) + Framer Motion + tokens.css + motion.ts + UiLabPage + frontend/CLAUDE.md

### Core / Runners

**Путь:** `src/botik/runners/`, `src/botik/core/`  
**Статус:** ✅ Работает (paper режим)  
- SpotRunner, FuturesRunner — paper trading
- RestPrivatePoller — offline если нет API ключей
- ProcessManager — subprocess для BackfillWorker, LiveDataWorker, TrainingWorker

### Data / ML

**Путь:** `src/botik/data/`, `src/botik/ml/`  
**Статус:** ✅ M0-M6 выполнены  
- BackfillWorker (REST история), LiveDataWorker (WS kline)
- TrainingPipeline — один проход price_history → fit()
- Baseline v2: futures hist=0.681/pred=0.710, spot hist=0.689/pred=0.721
- MIN_ACCURACY_TO_DEPLOY = 0.52

### Storage

**Путь:** `src/botik/storage/`  
**Статус:** ✅ SQLite (основная) + PostgreSQL (через DB_URL)  
- 10 миграций, 31+ таблица
- PostgreSQL: DB_URL=postgresql://botik:botik123@localhost:5432/botik

### Control (Telegram)

**Путь:** `src/botik/control/telegram_bot.py`  
**Статус:** ✅ 6 команд, schema-aware queries

### CI/CD

**Путь:** `.github/workflows/windows-package.yml`  
**Статус:** ✅ Авто-сборка exe по тегу v*, GitHub Release

### Tests / Visual track

**Путь:** `tests/visual/`, `tests/vision/`, `tests/unit/`, `docs/testing/`
**Статус:** ✅ Post-M1 cleanup (2026-04-26) — research-grade vision stack retired, focused product tests остались.

Active test stack:
- **Unit tests** (`tests/unit/python/` + integration в `tests/`): 253 tests collected, 22 unit за 1.3s.
- **Visual** (`tests/visual/`): `regression.spec` + `regions.spec` + `states.spec` (pixel diff с baselines в `baselines/`), `layout.spec` + `text-clip.spec` (JS-based, no baselines), `semantic.spec` + `semantic.helpers.ts` (`data-ui-*` контракт + canonical enums RUNTIME_STATE / JOBS_STATE / ACTION_STATE / MODEL_STATE).
- **Live product smoke** (`tests/visual/live-product-smoke.spec.ts`): real backend + Vite, no mocks, no vision. 5 routes (/, /runtime, /jobs, /spot, /models) — backend HTTP + DOM + semantic snapshot agreement. **5/5 ✅** на backend 8765 + Vite 4173 (2026-04-26).
- **Vision** (`tests/vision/vision.spec.ts`): Claude API (`VISION_MODE=llm` + `ANTHROPIC_API_KEY`) или JS heuristic. `VISION_STRICT=1` — fails on `severity=high AND confidence>0.7`.
- **Desktop-smoke** (`tests/desktop-smoke/`): browser-only headless Chromium против Vite + app-service. Не открывает Tauri window.
- **Desktop-native smoke** (`tests/desktop-native/run-automated-smoke.ps1`): launches real Tauri exe `apps/desktop/src-tauri/target/release/botik_desktop.exe`, asserts HWND visible, captures screenshot, kills process. Win32 P/Invoke (`lib/Win32Window.ps1`), no CDP/WebView2 framework. **PASSED** 2026-04-26 (window 1296×809, title='Botik').

Retired в M1 cleanup 2026-04-26 (external backup `C:/ai/aiBotik_legacy_backup_2026-04-26/`):
- `live-backend.spec.ts`, `interaction.spec.ts`, `region-guardrail.spec.ts` — vision-anchored, скиплись без `OLLAMA_VISION=1`.
- `agent_audit.spec.ts`, `vision_loop/diff/discover/interpret`, `semantic_gap`, `auto_test_gen` — research stack.
- `tests/desktop-native/` — использовал удалённый PyInstaller `botik_desktop.exe`.

---

## Активные / ожидающие задачи

| Задача | Статус | Примечание |
|--------|--------|------------|
| UI-Foundation (Tailwind v4 + shadcn/ui + Framer Motion) | ✅ done | 259 py OK, tsc OK, /ui-lab route существует |
| BLOCKER-2 (R1-R4) | 🔒 записан | Фактически все R1-R4 помечены ✅ done в WORKPLAN |
| BLOCKER-3 (demo API spot) | 🔒 записан | Требует demo API ключей |

---

## Команды запуска

```bash
# Primary desktop path (Tauri shell + sidecar app-service)
pwsh ./scripts/run-primary-desktop.ps1

# Frontend (dev, browser preview)
cd frontend && pnpm dev

# Backend (sidecar / dev, без shell)
pip install -r requirements.txt
python -m src.botik.main --config config.yaml

# Tests
pytest
ruff check .

# Visual + local vision loop (needs dev servers + Ollama + gemma3:4b)
OLLAMA_VISION=1 npx playwright test tests/visual/interaction.spec.ts --config tests/visual/playwright.visual.config.ts
# Live backend vision (real backend + real frontend, NO mocks)
OLLAMA_VISION=1 npx playwright test tests/visual/live-backend.spec.ts --config tests/visual/playwright.visual.config.ts
# Exploratory agent audit (report-only)
OLLAMA_AGENT=1 npx playwright test tests/vision/agent_audit.spec.ts --config tests/vision/playwright.vision.config.ts

# Native desktop shell (real botik_desktop.exe + real Win32 window, NO browser)
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-automated-smoke.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-visible-review.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\desktop-native\run-visible-review.ps1 -TearDown

# Browser-based desktop smoke (headless Chromium против Vite, НЕ открывает Tauri окно)
.\scripts\test-desktop-smoke.ps1

# Data bootstrap
python -m src.botik.runners.data_runner
python -m src.botik.runners.data_runner --once --skip-bootstrap
```
