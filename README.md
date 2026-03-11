# Botik

Botik — торговый бот с Dashboard Shell и ML-сервисом для двух торговых доменов:
- Spot holdings / orders
- Futures positions / orders / protection

Проект работает как единое desktop-приложение (single window Dashboard) и как headless runtime для server/systemd.

## Что сейчас поддерживается

- Dual-domain storage и runtime wiring (shared + spot + futures).
- Reconciliation при старте и по расписанию.
- Futures protection lifecycle с verify-from-exchange.
- Legacy write-path сохранён для обратной совместимости.
- Windows single-exe запуск через `src/botik/windows_entry.py`.
- Отдельный Spot Workspace для операторской работы с inventory lifecycle:
  - Spot Holdings (class/policy/stale/recovered visibility),
  - Spot Open Orders (domain `spot_orders`),
  - Spot Fills (`spot_fills`),
  - Spot Exit Decisions / inventory actions (`spot_exit_decisions`).

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

## Dashboard Workspaces (актуально)

- Dashboard Home: статусы, quick actions, блок Loaded Components / Releases.
- Spot Workspace: inventory-aware контроль holdings/orders/fills/exit decisions, safe policy labels.
- Futures Training Workspace: только training/research (не trading terminal).
- Telegram Workspace: модуль Telegram и его operational status.
- Logs Workspace: фильтруемые runtime логи.
- Ops Workspace: reconciliation/issues/audit/health.
- Settings Workspace: profile/paths/runtime settings.

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

### Packaged mode (основной пользовательский сценарий)

- Dashboard по умолчанию: `botik.exe`
- headless trading: `botik.exe --nogui --role trading --config config.yaml`
- headless ML: `botik.exe --nogui --role ml --config config.yaml --ml-mode online`

Важно:
- в packaged режиме кнопки `Start Trading` / `Start ML` внутри Dashboard запускают subprocess через тот же `botik.exe` (`--nogui --role ...`);
- путь `python -m ...` в packaged режиме не используется как default.

### Source/dev mode

- Dashboard: `python -m src.botik.gui.app`
- trading runtime: `python -m src.botik.main --config config.yaml`
- ML runtime: `python -m ml_service.run_loop --config config.yaml --mode online`

`run_windows_gui.bat` — только helper для source/dev запуска, не основной UX для конечного пользователя.

### Windows packaged entry

- entrypoint: `src/botik/windows_entry.py`
- маршрутизация ролей для `--nogui`: `trading | ml`

## ML service

Режимы:
- `bootstrap`
- `train`
- `predict`

## Версии Shell и компонентов

- `VERSION` — источник `Dashboard Shell Version` (semver patch) и build number.
- `version.txt` — build SHA (обычно текущий git commit для build/release).
- `dashboard_release_manifest.yaml` — версии компонентов и release metadata, которые Dashboard Home читает в блоке `Loaded Components / Releases`.

## Документация

- [docs/PLAN.md](docs/PLAN.md)
- [docs/PROD_RUNBOOK.md](docs/PROD_RUNBOOK.md)
- [docs/WINDOWS_PACKAGING.md](docs/WINDOWS_PACKAGING.md)
- [docs/AGENT_PROMPTS.md](docs/AGENT_PROMPTS.md)
