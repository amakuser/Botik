# Botik — Текущее состояние проекта

> Обновлять перед каждым значимым шагом (правило #4 в CLAUDE.md).
> Последнее обновление: 2026-04-25

---

## Стек

- **Backend:** Python 3.11, pybit (Bybit API), SQLite + PostgreSQL
- **Frontend:** React 19 + TypeScript + Vite + Tauri (мигрирован с pywebview 2026-04-18)
- **ML:** scikit-learn / PyTorch, pandas / numpy
- **Infra:** GitHub Actions CI, pyinstaller exe, PostgreSQL 18 (windows direct)

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

**Путь:** `tests/visual/`, `tests/vision/`, `docs/testing/`
**Статус:** ✅ Production-grade — semantic auto-region + canonical state layer (2026-04-25)

- `tests/visual/semantic.helpers.ts` — `collectSemanticRegions` / `captureSemanticSnapshot` / `compareSemanticSnapshots` через `data-ui-*`. Канонические enums: `RUNTIME_STATE.{INACTIVE,ACTIVE,DEGRADED}`, `JOBS_STATE.{EMPTY,NON_EMPTY}`, `ACTION_STATE.{ENABLED,DISABLED}`. Каждый регион несёт `state` (raw) и `canonical_state` (typed enum). Diff сравнивает canonical, raw fallback только когда оба unmapped.
- `data-ui-*` контракт размечен на `RuntimeStatusCard` и на 5 jobs-компонентах (`JobMonitorPage`, `JobToolbar`, `DataBackfillJobCard`, `DataIntegrityJobCard`, `JobStatusCard`). Не заменяет `data-testid`.
- `tests/visual/live-backend.spec.ts` (6 сценариев): health, runtime, jobs (read-only) + 3 live-interaction (start spot / stop spot / start futures) с multi-region (header + actions + callouts), `composeDecision`, `checkRegionLayoutSanity`, и semantic snapshot/diff на canonical уровне.
- `tests/visual/semantic.spec.ts` (5 тестов): runtime contract, jobs contract, state-flip diff, `canonical state survives a UI rename` (synthetic safety-net), action availability flip.
- `tests/visual/region-guardrail.spec.ts` (1) — proves classifiers skip regions < `VISION_REGION_MIN` без вызова модели.
- `tests/visual/interaction.spec.ts` (4) — vision integrated, OLLAMA_VISION=1.
- Last runtime verification: **16/16 ✅** на живом стеке (backend 8765 v0.0.77 + Vite 4173 + Ollama 11434 + gemma3:4b).

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
# Backend
pip install -r requirements.txt
python main.py

# Frontend (dev)
cd frontend && pnpm dev

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
