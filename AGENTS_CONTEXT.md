# AGENTS_CONTEXT.md — Общая доска агентов

> Читается и обновляется каждым агентом и оркестратором.
> Сбрасывается в начале каждой новой задачи.

---

## Текущая задача

_Нет активной задачи_

---

## Задания агентам

_Пусто_

---

## Результаты агентов

### Core/Data-агент — модуль бэктестинга (2026-04-05)

**Статус:** ✅ завершено

**Что создано:**

1. **`src/botik/backtest/__init__.py`** — реэкспорт `BacktestResult`, `BacktestRunner`, `FuturesBacktestRunner`, `SpotBacktestRunner`

2. **`src/botik/backtest/backtest_result.py`** — `@dataclass BacktestResult` со всеми полями и методом `to_dict()`

3. **`src/botik/backtest/backtest_runner.py`** — иерархия:
   - `_BaseBacktestRunner` — загрузка свечей из `price_history`, торговый цикл, вычисление метрик (drawdown, Sharpe, profit_factor)
   - `FuturesBacktestRunner` — in-memory long/short, category='linear', комиссия 0.055%
   - `SpotBacktestRunner` — in-memory long only, category='spot', комиссия 0.1%

4. **`tests/test_backtest.py`** — 13 тестов

**Результат тестов:**
```
13 passed in 1.96s
```

Все 13 тестов прошли:
- `test_backtest_result_to_dict` ✅
- `test_backtest_result_win_rate_zero_trades` ✅
- `test_futures_backtest_runner_no_data` ✅
- `test_futures_backtest_runner_single_candle` ✅
- `test_futures_backtest_basic` ✅
- `test_spot_backtest_basic` ✅
- `test_backtest_profit_factor_no_losses` ✅
- `test_backtest_max_drawdown` ✅
- `test_calc_sharpe_too_few_trades` ✅
- `test_calc_sharpe_stable_returns` ✅
- `test_calc_profit_factor_no_wins` ✅
- `test_futures_runner_scope_and_category` ✅
- `test_spot_runner_scope_and_category` ✅

**Зависимость закрыта:**
- GUI-агент ожидал `FuturesBacktestRunner` / `SpotBacktestRunner` — теперь доступны.

---

### GUI-агент — страница Бэктест (2026-04-05)

**Статус:** ✅ завершено

**Что создано / изменено:**

1. **`src/botik/gui/api_backtest_mixin.py`** — новый файл
   - Класс `BacktestMixin` с методами:
     - `run_backtest(scope, symbol, interval, days_back, balance)` — синхронный запуск через `FuturesBacktestRunner` / `SpotBacktestRunner`, graceful fallback при `ImportError`
     - `get_backtest_symbols()` — `SELECT DISTINCT symbol FROM symbol_registry WHERE is_active=1`, fallback список из 5 пар
   - py_compile: ✅ OK

2. **`src/botik/gui/webview_app.py`** — добавлен импорт `BacktestMixin` и включён в базовые классы `DashboardAPI`
   - py_compile: ✅ OK

3. **`dashboard_preview.html`** — добавлены:
   - Nav-item `data-page="backtest"` в боковой панели (раздел Система, между Telegram и Настройки)
   - Страница `#page-backtest`: форма параметров (scope/symbol/interval/days_back + кнопка), спиннер, сетка 2×4 метрик, мета-строка, таблица сделок (последние 50)
   - CSS анимация `@keyframes spin` для спиннера
   - JS функции: `_loadBacktestPage()`, `apiGetBacktestSymbols()`, `apiRunBacktest()`, `_runBacktest()`, `_renderBacktestResult()`, `_btHideAll()`, `_btShowError()`
   - Обработчик навигации: `if (page === 'backtest') { _loadBacktestPage(); }`

**Зависимость от параллельного агента:**
- Ожидается `src/botik/backtest/backtest_runner.py` с классами `FuturesBacktestRunner` / `SpotBacktestRunner`.
- При его отсутствии — mixin возвращает `{"error": "backtest_runner not available: ..."}`, JS показывает сообщение об ошибке. Страница работает без краша.

---

## Зависимости между агентами

_Нет активных зависимостей_

---

## Незакрытые вопросы

_Нет_
