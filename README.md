# Botik

Botik — торговый бот с Dashboard Shell и ML-сервисом для двух торговых доменов:
- Spot holdings / orders
- Futures positions / orders / protection

Botik is a Windows-first Tauri desktop trading workstation.

Active product path:
- Tauri desktop shell (Rust)
- React + TypeScript frontend (Vite, Tailwind v4)
- FastAPI app-service sidecar
- `src/botik/*` domain/runtime
- local SQLite (PostgreSQL via `DB_URL` опционально)
- local ML / Ollama as needed

Legacy pywebview, PyInstaller (`botik.spec`, `scripts/build-exe.ps1`), root `core/`/`strategies/`/`main.py` and SPA `dashboard_*manifest.yaml` are retired and moved to external backup `C:/ai/aiBotik_legacy_backup_2026-04-26/` (2026-04-26). They are no longer in the active repo.

Linux/server headless mode is **not** the current primary path. `src/botik` runtime can run as a sidecar under the Tauri shell on Windows; pure server/systemd deployment is documented as future/advanced, not main path.

Текущее состояние оболочки:
- современный dark Dashboard Shell с более мягкой визуальной иерархией;
- русифицированные top-level labels (`Главная`, `Спот`, `Фьючерсы`, `Модели`, `Логи`, `Состояние`, `Настройки`);
- scrollable text/log/status areas с нормальной прокруткой колесом мыши;
- hidden subprocess path без видимых cmd/console окон.

## Что сейчас поддерживается

- Primary desktop GUI path через новый shell:
  - `/jobs`
  - `/logs`
  - `/runtime`
  - `/spot`
  - `/futures`
  - `/telegram`
  - `/analytics`
  - `/models`
  - `/diagnostics`
- Dual-domain storage и runtime wiring (shared + spot + futures).
- Reconciliation при старте и по расписанию.
- Futures protection lifecycle с verify-from-exchange.
- Legacy write-path сохранён для обратной совместимости.
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

## Visual / UX polish

- Dashboard Shell использует более чистую dark palette, крупные cards и более мягкие отступы.
- Длинные status/release/model panels разбиты на более читаемые строки вместо плотных multi-line blobs.
- Колесо мыши работает в логах, таблицах и scrollable text/status panels через единый shell-level wiring.
- Визуальный polish не меняет runtime/business logic и не ломает hidden subprocess path.

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

### Primary desktop path

- source/dev default GUI: `pwsh ./scripts/run-primary-desktop.ps1`
- packaged default GUI: Tauri desktop shell build from `apps/desktop`

Важно:
- primary desktop shell остаётся host-owned оболочкой и не берёт на себя business orchestration;
- app-service sidecar стартует и завершается под управлением shell;
- migrated surfaces проверяются через headless E2E и desktop smoke;
- rollback после legacy retirement выполняется через git history или revert retirement PR, а не через поддерживаемый fallback launcher.

### Headless runtime paths (advanced, not primary)

- trading runtime: `python -m src.botik.main --config config.yaml`
- ML runtime: `python -m ml_service.run_loop --config config.yaml --mode online`

These are used by Tauri shell as sidecars or for advanced/future server deployment. Не основной путь оператора — primary GUI/product path = Tauri desktop shell.

## ML service

Режимы:
- `bootstrap`
- `train`
- `predict`

## Версии Shell и компонентов

- `VERSION` — источник `Dashboard Shell Version` (semver patch) и build number.
- `version.txt` — build SHA (обычно текущий git commit для build/release).
- `active_models.yaml` — внешний source of truth для `active_spot_model` / `active_futures_model`. Подхватывается без пересборки desktop binary.

`Model Registry Workspace` использует externalized model selector-схему так:
- promotion модели обновляет `active_models.yaml` по конкретному инструменту,
- legacy `model_registry.is_active` синхронизируется только в пределах того же instrument-slot,
- Spot и Futures больше не делят один глобальный active model slot.

Legacy `dashboard_release_manifest.yaml` / `dashboard_workspace_manifest.yaml` retired 2026-04-26 — описывали SPA, которой больше нет; перенесены во внешний backup. Frontend / app-service / src/botik их не читают.

## Документация

- [docs/PLAN.md](docs/PLAN.md)
- [docs/PROD_RUNBOOK.md](docs/PROD_RUNBOOK.md)
- [docs/WINDOWS_PACKAGING.md](docs/WINDOWS_PACKAGING.md)
- [docs/AGENT_PROMPTS.md](docs/AGENT_PROMPTS.md)
- [docs/architecture/README.md](docs/architecture/README.md)
- [docs/architecture/process-lifecycle.md](docs/architecture/process-lifecycle.md)
- [docs/testing/testing-strategy.md](docs/testing/testing-strategy.md)
- [docs/testing/selectors-and-test-ids.md](docs/testing/selectors-and-test-ids.md)
- [docs/testing/artifact-retention.md](docs/testing/artifact-retention.md)
- [docs/dev-workflow/development-workflow.md](docs/dev-workflow/development-workflow.md)
- [docs/ci/minimal-ci-plan.md](docs/ci/minimal-ci-plan.md)
- [docs/migration/rollback-plan.md](docs/migration/rollback-plan.md)
- [docs/migration/legacy-retirement.md](docs/migration/legacy-retirement.md)
