# Botik

Botik — торговый бот с Dashboard Shell и ML-сервисом для двух торговых доменов:
- Spot holdings / orders
- Futures positions / orders / protection

Проект работает как единое desktop-приложение (single window Dashboard) и как headless runtime для server/systemd.

Текущее состояние оболочки:
- современный dark Dashboard Shell с более мягкой визуальной иерархией;
- русифицированные top-level labels (`Главная`, `Спот`, `Фьючерсы`, `Модели`, `Логи`, `Состояние`, `Настройки`);
- scrollable text/log/status areas с нормальной прокруткой колесом мыши;
- hidden subprocess path без видимых cmd/console окон.

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

- Главная: статусы, quick actions, блок `Компоненты и релизы` и два независимых instrument cards:
  - Spot block:
    - runtime status,
    - active holdings / open orders / recovered / stale,
    - active spot model,
    - mini settings snapshot (`TP`, `SL`, `max_position_size`, `hard_rules`, `training_source`, `dust_threshold`),
    - actions: `Старт`, `Стоп`, `Открыть спот`, `Логи спота`.
  - Futures block:
    - training status,
    - paper results summary (`good / bad / closed results`),
    - active futures model,
    - mini settings snapshot (`TP`, `SL`, `max_position_size`, `hard_rules`, `training_source`),
    - actions: `Старт обучения`, `Пауза обучения`, `Открыть фьючерсы`, `Логи фьючерсов`.
- Spot start/stop on Home теперь управляют только spot runtime modes и не поднимают futures/training процессы автоматически.
- Блок `Компоненты и релизы` на Главной теперь показывает структурированно:
  - release / workspace / active-models manifest statuses,
  - Dashboard Shell version + build SHA + version sources,
  - component versions,
  - active spot/futures models и active profile,
  - manifest file names и workspace order.
- Спот: inventory-aware контроль holdings/orders/fills/exit decisions, safe policy labels.
  - Spot Strategy Presets теперь живут здесь же, рядом с spot runtime actions, а не в Settings Workspace.
  - `Start Spot` / `Stop Spot` в Spot Workspace управляют только spot runtime modes и не тянут futures research flow.
- Фьючерсы: верхнеуровневое рабочее пространство для futures research/paper-потоков, без маскировки под live trading terminal.
  - Futures Training Workspace:
    - Training Status Summary,
    - Dataset / Candles,
    - Feature & Label Pipeline,
    - Training Run Progress,
    - Evaluation / Metrics Summary,
    - Checkpoints / Active Futures Model,
    - Futures Research Preset (`Futures Spike Reversal`) с отдельной apply-path внутри Futures Workspace.
  - Futures Paper Workspace:
    - paper positions snapshot,
    - pending futures orders,
    - closed paper results с `good / bad / flat` по финальному `net_pnl_quote`,
    - read-only status line с честным `close_controls=unsupported / reset_session=unsupported`,
    - paper-only actions и переход в Model Registry Workspace.
- Модели: champion/challenger реестр моделей, выбор активной модели и сравнение результатов.
  - summary по spot/futures/unknown model slots,
  - role-aware view (`champion:spot`, `champion:futures`, `legacy-active`, `candidate`),
  - instrument / policy / source / outcomes / net PnL / artifact path,
  - selector summary line теперь отдельно подсказывает `hold / review / prefer` для spot и futures champion slots,
  - actions: `Promote Selected to Active`, `Compare Selected Models`, `Open Model Stats`, `Copy Artifact Path`.
  - source of truth для champion pointers — `active_models.yaml`; legacy `model_registry.is_active` удерживается только для compatibility.
- Telegram: отдельный operational module Dashboard (не buried toggle в Settings):
  - Telegram Status Summary (enabled/connected/profile/module version),
  - Bot Profile / Connection (token configured yes/no, startup status),
  - Allowed Chats / Access (masked IDs, restrictions),
  - Available Commands (только реально поддерживаемые),
  - Recent Incoming Commands / Recent Alerts / Telegram Errors,
  - Telegram Actions: Refresh, Test Send (intent only), Reload Telegram Status, Open Logs, Open Settings/Profile.
- Если `TELEGRAM_BOT_TOKEN` не задан, Telegram Workspace показывает `disabled / configuration_missing_token` и не имитирует активный модуль.
- Логи: фильтруемые runtime логи.
  - filters: `channel`, `instrument`, `pair`, `severity`, `query`
  - quick routes: `Spot`, `Futures`, `Telegram`, `Ops`, `Errors`
  - `Open Spot Logs` / `Open Futures Logs` / `Open Telegram Logs` теперь открывают Logs Workspace уже с преднастроенными filters, а не просто переводят на пустой общий log view.
- Состояние: reconciliation/issues/audit/health.
  - operational cards: `Runtime Services`, `Reconciliation`, `Protection / Risk`, `DB / Freshness`, `Capabilities`
  - quick actions: `Refresh`, `Open Ops Logs`, `Focus Issues`, `Focus Futures Positions`
  - keeps active issues, resolved issues, protection status and freshness visible without overloading Dashboard Home.
- Настройки: technical-only surface для:
  - `.env` secrets / API keys / Telegram refs,
  - launcher diagnostics (`source` / `packaged`, runtime executable, config profile),
  - external manifest paths (`dashboard_release_manifest.yaml`, `dashboard_workspace_manifest.yaml`, `active_models.yaml`),
  - technical runtime fields (`execution.mode`, `start_paused`, `bybit.host`, `ws_public_host`).
- Instrument-level knobs (`TP/SL`, `training_source`, strategy presets, policy controls) intentionally removed from Settings Workspace and live in Dashboard Home, Spot Workspace or Futures Workspace.

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

### Packaged mode (основной пользовательский сценарий)

- Dashboard по умолчанию: `botik.exe`
- headless trading: `botik.exe --nogui --role trading --config config.yaml`
- headless ML: `botik.exe --nogui --role ml --config config.yaml --ml-mode online`

Важно:
- в packaged режиме кнопки `Start Trading` / `Start ML` внутри Dashboard запускают subprocess через тот же `botik.exe` (`--nogui --role ...`);
- путь `python -m ...` в packaged режиме не используется как default.
- subprocess-воркеры Dashboard запускаются через internal supervisor path, без видимых console windows на Windows.
- start/stop/training actions уходят в background dispatch и не должны подвешивать Dashboard Shell во время process launch/stop.

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
- `active_models.yaml` — внешний source of truth для `active_spot_model` / `active_futures_model`, который Dashboard Home и Futures Workspace читают поверх release manifest.

На Home эти источники показываются раздельно:
- `release manifest status`
- `workspace manifest status`
- `active models manifest status`
- `shell version source`
- `shell build source`

## Externalized Dashboard Model

Dashboard Shell использует внешние manifests как источник операционного состояния без обязательной пересборки `botik.exe`.

Основные внешние файлы:
- `dashboard_release_manifest.yaml`:
  - версии компонентов (`workspace_pack`, `spot_runtime`, `futures_training_engine`, `telegram_bot_module`, `db_schema`),
  - активный config profile.
- `dashboard_workspace_manifest.yaml`:
  - порядок, видимость и display labels workspaces (`enabled/visible/order/label`).
- `active_models.yaml`:
  - pointers на `active_spot_model` и `active_futures_model`,
  - optional checkpoint paths.

`Model Registry Workspace` использует эту externalized model selector-схему так:
- promotion модели обновляет `active_models.yaml` по конкретному инструменту,
- legacy `model_registry.is_active` синхронизируется только в пределах того же instrument-slot,
- Spot и Futures больше не делят один глобальный active model slot.

Что Dashboard подхватывает без rebuild EXE:
- изменения в `dashboard_release_manifest.yaml`,
- изменения порядка/visibility/labels в `dashboard_workspace_manifest.yaml`,
- изменения `active_spot_model` / `active_futures_model` в `active_models.yaml`,
- изменения config profiles и runtime metadata, которые уже вынесены в файлы (`config.yaml`, `.env`, data manifests).

Что обычно требует rebuild:
- изменения кода Dashboard Shell,
- изменения launcher/entrypoint behavior,
- изменения встроенной логики runtime/ML, которые не externalized через manifests.

Fallback behavior:
- при `missing/malformed` manifest Dashboard не падает,
- применяется безопасный defaulted layout/status,
- Home показывает фактический статус загрузки (`loaded/missing/failed/defaulted`) для manifests.

## Dashboard Service Supervision

Dashboard Shell сам управляет runtime workers:
- Spot runtime,
- ML / Futures Training runtime,
- one-shot preflight tasks.

Текущее поведение:
- workers стартуют из кода, а не через `.bat` как user-facing UX,
- на Windows используется hidden subprocess launch path,
- действия `Start/Stop/Training` отправляются в background dispatcher,
- Dashboard показывает состояние сервисов через status/read-model layer, а не требует ручной terminal orchestration.

## Документация

- [docs/PLAN.md](docs/PLAN.md)
- [docs/PROD_RUNBOOK.md](docs/PROD_RUNBOOK.md)
- [docs/WINDOWS_PACKAGING.md](docs/WINDOWS_PACKAGING.md)
- [docs/AGENT_PROMPTS.md](docs/AGENT_PROMPTS.md)
