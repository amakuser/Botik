# Botik

Botik — торговый бот с GUI и ML-сервисом для двух торговых доменов:
- Spot holdings / orders
- Futures positions / orders / protection

Проект работает как единое desktop-приложение (single window GUI) и как headless runtime для server/systemd.

## Что сейчас поддерживается

- Dual-domain storage и runtime wiring (shared + spot + futures).
- Reconciliation при старте и по расписанию.
- Futures protection lifecycle с verify-from-exchange.
- Legacy write-path сохранён для обратной совместимости.
- Windows single-exe запуск через `src/botik/windows_entry.py`.

## Архитектура доменов

### Shared core

Основные общие сущности:
- `account_snapshots`
- `reconciliation_runs`
- `reconciliation_issues`
- `strategy_runs`
- `events_audit`
- `model_registry`

### Spot domain

Отдельные таблицы и поток записей:
- `spot_balances`
- `spot_holdings`
- `spot_orders`
- `spot_fills`
- `spot_position_intents`
- `spot_exit_decisions`

### Futures domain

Отдельные таблицы и поток записей:
- `futures_positions`
- `futures_open_orders`
- `futures_fills`
- `futures_protection_orders`
- `futures_position_decisions`
- (дополнительно в схеме: funding/liquidation snapshots)

## Runtime path (кратко)

1. Startup:
- загрузка config/env,
- инициализация storage/schema,
- запуск executor,
- запуск reconciliation (если capability поддерживается).

2. Reconciliation:
- startup run до основного цикла,
- scheduled run по интервалу,
- фиксация `reconciliation_runs/issues` + `events_audit`,
- symbol-level lock для новых entry при открытых конфликтах.

3. Strategy loop:
- market data -> intents -> risk gates -> execution.

4. Protection/Risk:
- futures entry требует protection plan,
- `set_trading_stop` -> verify from exchange,
- статусы: `pending | protected | unprotected | repairing | failed`,
- новые futures entry блокируются при `pending/repairing/failed/unprotected`.

5. Domain writes:
- runtime пишет и в legacy таблицы (`orders`, `fills`), и параллельно в domain-таблицы.

## Reconciliation

Reconciliation запускается:
- автоматически на старте runtime,
- далее по `strategy.reconciliation_interval_sec`.

Если executor не поддерживает reconciliation capability, runtime:
- не симулирует успешную синхронизацию,
- пишет понятный warning/audit статус,
- безопасно отключает reconciliation loop.

## Futures protection lifecycle

Базовый lifecycle:
- после entry: `pending` (или `repairing` при повторной попытке),
- после успешного verify: `protected`,
- при неуспехе apply/verify: `unprotected` или `failed`.

Важно:
- `retCode=0` по `set_trading_stop` сам по себе недостаточен,
- требуется verify через `get_positions`.

## Paper mode: ограничения

Paper executor поддерживает базовый order flow для отладки цикла, но:
- protection capability = unsupported,
- reconciliation capability = unsupported,
- runtime явно это логирует и не показывает ложное “всё защищено/синхронизировано”.

Paper режим не предназначен для проверки реальной биржевой защиты futures-позиций.

## Запуск

### Desktop GUI (одно главное окно)

- `python -m src.botik.gui.app`
- или `run_windows_gui.bat`

### Runtime (CLI)

- `python -m src.botik.main --config config.yaml`

### Windows packaged entry

- entrypoint: `src/botik/windows_entry.py`
- GUI по умолчанию: `botik.exe`
- headless опционально: `botik.exe --nogui --config config.yaml`

## ML service

ML запускается отдельно от trading runtime:
- `python -m ml_service.run_loop --config config.yaml`

Режимы:
- `bootstrap`
- `train`
- `predict`

## Документация

- [docs/PLAN.md](docs/PLAN.md)
- [docs/PROD_RUNBOOK.md](docs/PROD_RUNBOOK.md)
- [docs/WINDOWS_PACKAGING.md](docs/WINDOWS_PACKAGING.md)
- [docs/AGENT_PROMPTS.md](docs/AGENT_PROMPTS.md)
