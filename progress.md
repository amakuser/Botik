# Botik — Текущее состояние проекта

> Обновлять перед каждым значимым шагом (правило #4 в CLAUDE.md).
> Последнее обновление: 2026-04-19

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
**Ждёт:** UI-Foundation (Tailwind v4 + shadcn/ui + Framer Motion) — агент подготовлен, не запущен

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

---

## Активные / ожидающие задачи

| Задача | Статус | Примечание |
|--------|--------|------------|
| UI-Foundation (Tailwind v4 + shadcn/ui + Framer Motion) | ⬜ ожидает | Задание готово в AGENTS_CONTEXT.md |
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

# Data bootstrap
python -m src.botik.runners.data_runner
python -m src.botik.runners.data_runner --once --skip-bootstrap
```
