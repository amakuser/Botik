# Agent Memory — trading-expert

> Читать перед началом работы. Обновлять после каждой нетривиальной задачи.

---

## Non-trivial solutions

### 2026-03-22 — Subprocess воркеры из frozen exe (pyinstaller)

**Проблема:** `sys.executable -m src.botik.data.backfill_entry` не работает из `botik.exe`
(pyinstaller frozen mode) — флаг `-m` не распознаётся exe.

**Решение:** `_build_subprocess_cmd(worker)` в `api_helpers.py`:
```python
def _build_subprocess_cmd(worker: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", worker]
    return [sys.executable, "-m", f"src.botik.data.{worker}_entry"]
```
В `windows_entry.py` добавлен dispatch по `--worker backfill|live|training`.

**Вывод:** Всегда проверять frozen mode при запуске subprocess. Все entry points
регистрировать в `windows_entry.py`.

---

### 2026-03-21 — Bybit demo trading vs testnet

**Проблема:** Bybit testnet имеет синтетические цены — не подходит для реалистичного тестирования.

**Решение:** Использовать demo trading (реальные рыночные цены, виртуальный баланс).
REST polling вместо private WebSocket (совместимо с demo ограничениями).

**Конфиг:**
- `BYBIT_API_KEY`, `BYBIT_API_SECRET` в `.env`
- `RestPrivatePoller` — при отсутствии ключей переходит в offline (строки 98-102)

**Вывод:** Demo API = api.bybit.com, не testnet. Ключи из demo аккаунта Bybit.

---

### 2026-03-21 — PositionSizer: risk_qty + Kelly только при is_trained

**Решение:** `PositionSizer` использует `risk_qty` по умолчанию. Kelly включается
только при `is_trained=True` в ModelRegistry.

**Вывод:** Не применять Kelly-подход без накопленной статистики — риск неадекватного
позиционирования на начальном этапе.

---

### 2026-03-22 — BackfillWorker: symbol discovery через Bybit public API

**Проблема:** Хардкод 5 символов не масштабируется.

**Решение:** `seed_symbol_registry()` — fetch_linear_instruments (~300-400 USDT perpetuals)
+ fetch_spot_instruments (~400-600 USDT pairs) × 4 интервала = ~2800-4000 строк.
Всегда использует `api.bybit.com` (не demo) — public endpoint, ключи не нужны.

**Вывод:** symbol_universe.py — единый модуль для получения торговой вселенной Bybit.

---

## Quirks & gotchas

- **Bybit API rate limits:** spot 20 req/s, futures 10 req/s. BackfillWorker делает паузы.
- **OHLCV pagination:** REST /v5/market/kline — 1000 свечей/запрос, порядок убывания.
  При backfill использовать `cursor` или `start`/`end` параметры.
- **WS kline:** Поле `confirm=true` — только закрытые свечи. Незакрытые игнорировать.
- **futures_positions колонки:** Два варианта — `size/unrealised_pnl` и `qty/unrealized_pnl`.
  Использовать schema introspection.
- **UNIQUE constraint:** `futures_protection_orders` — UNIQUE(symbol, side) + UPSERT.
  Иначе дубли и декартово произведение в JOIN.

---

## Current context

**Последняя задача:** T43 Таймфреймы backfill (4h/D/W) — ✅ выполнено (2026-04-07)
**Baseline v2 accuracy:** futures hist=0.681/pred=0.710, spot hist=0.689/pred=0.721
**Следующее:** Нет активных торговых задач. UI-Foundation приоритетна.

### 2026-04-19 — Верификация: структура памяти агента подтверждена

Проверка в рамках Full Verification Run.
Файл существует, структура корректна (Non-trivial solutions / Quirks / Current context).
Время: 2026-04-19 11:35:42
