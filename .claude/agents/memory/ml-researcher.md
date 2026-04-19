# Agent Memory — ml-researcher

> Читать перед началом работы. Обновлять после каждой нетривиальной задачи.

---

## Non-trivial solutions

### 2026-03-21 — bootstrap: limit_per_symbol слишком мал

**Проблема:** `trainer.bootstrap(scope="futures")` использовал `limit_per_symbol=2000` —
лабелер получал только 20 образцов из 43k свечей. Модель не обучалась.

**Исправление:** Поднято до `limit_per_symbol=40000`.
**Результат:** 2244 futures / 2023 spot образцов — достаточно для обучения.

**Вывод:** При bootstrap всегда проверять реальное количество labeled_samples. Если <100 — проблема в limit.

---

### 2026-03-21 — registry._write_db: колонка model_name не существует

**Проблема:** INSERT в `model_stats` использовал колонку `model_name` (не существует в схеме).
Откатывал весь transaction включая запись в `ml_training_runs`.

**Исправление:** Заменить на `model_id`.

**Вывод:** Перед INSERT в model_stats — проверять схему через PRAGMA table_info.
`model_stats` колонки: `model_id, model_scope, accuracy, ...` (не `model_name`).

---

### 2026-03-21 — registry._get_latest_version: LIKE по model_version не работает

**Проблема:** Паттерн `futures_historian_%` по колонке `model_version` которая хранит `v1`, `v2`.
Никогда не совпадало.

**Исправление:** Сначала glob по файлам на диске (надёжно), fallback в БД.

**Вывод:** Версии моделей — по файлам на диске, не по БД. БД как вторичный источник.

---

### 2026-03-22 — TrainingPipeline: chunked reading для экономии памяти

**Проблема:** `_read_candles()` загружала всю `price_history` в память — O(всей_истории).

**Решение:** `_read_candles_chunk()` с LIMIT/OFFSET пагинацией, chunk=10K строк,
tail=29 свечей (_TAIL_SIZE=MIN_CANDLES+FORWARD_CANDLES-1).

**Результат:** Пиковая память O(CHUNK_SIZE) вместо O(всей_истории).
Граничные позиции не теряются благодаря overlapping tail.

**Вывод:** Для price_history всегда использовать chunked reading.

---

### 2026-03-22 — labeled_samples: только для live feedback, не для обучения

**Решение:** labeled_samples НЕ используется в TrainingPipeline.
Только для live trade feedback (OutcomeLearner, weight=3.0).

**Вывод:** Обучение: `price_history → фичи в памяти → model.fit()` — один проход.
labeled_samples = только веса от реальных сделок.

---

## Quirks & gotchas

- **MIN_ACCURACY_TO_DEPLOY = 0.52** — порог для сохранения моделей через ModelRegistry.save()
- **Веса:** исторические образцы weight=1.0, live trades weight=3.0
- **active_models.yaml** — манифест активных моделей. Читается через _load_yaml() из api_helpers.
- **ml_training_runs** колонки: `model_id` (не `model_name`), `model_scope`, `accuracy`
- **model_stats** колонки: могут быть в двух вариантах — проверять через introspection
- **Lookahead bias:** данные для обучения строго ДО данных для валидации (временная ось)

---

## Current context

**Baseline v2 (зафиксировано 2026-03-21):**
- futures: hist_accuracy=0.681, pred_accuracy=0.710
- spot: hist_accuracy=0.689, pred_accuracy=0.721

**Последняя задача:** M0-M6 полностью выполнены (2026-03-22) — ✅  
**Следующее:** Нет активных ML задач. UI-Foundation приоритетна для текущей волны.
