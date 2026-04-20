# WORKPLAN — Botik Trading Bot

> Динамический план работ. Читается перед началом каждой рабочей сессии.
> Текущая структура нормализована и дополнена Codex 2026-03-21.
> Этот файл хранит активные шаги, блокеры, историю решений и точки обязательного возврата.
> Все записи в этом файле ведутся на русском языке.

---

## Легенда статусов

| Статус | Значение |
|--------|----------|
| ✅ done | Выполнено и проверено |
| 🔄 active | Выполняется сейчас |
| ⏸ partial | Частично выполнено, требуется обязательный возврат |
| 🔒 blocked | Заблокировано зависимостью или внешним условием |
| ⬜ waiting | Ожидает своей очереди |
| 🔁 follow-up | Запланированный возврат к ранее начатому шагу |

---

## Active plan

| ID | Задача | Статус | Зависит от | Разблокирует | Следующее действие | Причина или примечание |
|----|--------|--------|------------|--------------|--------------------|------------------------|
| F1 | БД: миграции (10 миграций, 31 таблица) | ✅ done | — | 1, 11, 13 | Поддерживать без регрессий | Базовая схема уже в проекте |
| F2 | pywebview дашборд вместо tkinter | ✅ done | — | 8, 9, 10, 15 | Поддерживать без регрессий | Базовый desktop UI уже переведён на pywebview |
| 1 | Настройки: API ключи в UI + `.env` + DB | ✅ done | F1 | 6, R5 | Дополнять настройки только без ломки текущей схемы | Базовая настройка уже реализована |
| 2 | Логи: 5 суб-вкладок (`sys/spot/futures/ml/telegram`) | ✅ done | F2 | 15 | Поддерживать текущую структуру логов | Базовый набор вкладок уже реализован |
| 3 | Telegram: 6 новых команд | ✅ done | 1 | 14 | Поддерживать команды на schema-aware ридерах БД и не возвращаться к legacy-полям | `/orders` и `/futures` переведены на актуальные выборки и учитывают переходные варианты схем `spot_holdings` и `futures_positions` |
| 4 | Фьючерсы: paper engine + runner | ✅ done | F1 | 5, 8, 14 | Поддерживать runtime без регрессий | Фьючерсный paper runtime уже в проекте |
| 5 | ML: три модели + trainer + labeler | ✅ done | 13 | 14, 12 | Поддерживать без регрессий | Bootstrap завершён: futures hist=0.681 pred=0.710 v2; predict_fn проводка верифицирована по коду FuturesRunner:103–105 |
| 6 | Спот: paper engine + runner + REST poller | ✅ done | 13 | 7, 9, 14 | Поддерживать без регрессий | Bootstrap spot завершён; RestPrivatePoller читает BYBIT_API_KEY/SECRET из env и корректно переходит в offline если ключи не заданы; проводка R5 верифицирована по коду |
| 7 | Спот: ML модели (`scope=spot`) | ✅ done | 6 | 10, 14 | Поддерживать без регрессий | Bootstrap spot: hist=0.689 pred=0.721 v2; _predict_fn проводка верифицирована по коду SpotRunner:121–128,321–334 |
| 8 | Дашборд: вкладка Фьючерсы | ✅ done | F2 | 15 | Поддерживать live-привязку futures-метрик и таблицы позиций во `webview`-дашборде | Codex 2026-03-21: убрана заглушка, исправлено чтение `futures_positions`, добавлены реальные summary-метрики и автообновление таблицы |
| 9 | Дашборд: вкладка Спот | ✅ done | F2 | 15 | Поддерживать `spot`-страницу на live summary и переключаемых наборах данных (`Позиции / Ордера / История`) | Codex 2026-03-21: spot-ридер переведён на актуальную schema, добавлены live summary-метрики и отдельные API-методы для orders/fills |
| 10 | Дашборд: вкладка Модели (ML статус) | ✅ done | F2 | 15 | Поддерживать вкладку на schema-aware read model из `active_models.yaml`, `ml_training_runs` и `model_stats` | Codex 2026-03-21: вкладка `Модели` переведена с заглушек на live summary, карточки `spot/futures` и таблицу последних training runs; `webview_app.py` больше не зависит от legacy SQL по `model_name/model_type/symbol` |
| 11 | PostgreSQL: миграции + smoke-test | ✅ done | F1 | 14, 12 | Поддерживать без регрессий | PostgreSQL 18 установлен напрямую; `_sqlite_to_pg()` добавлена в `db.py`; smoke-test: 10 миграций OK, все таблицы созданы; `DB_URL=postgresql://botik:botik123@localhost:5432/botik` |
| 12 | Пересборка `botik.exe` | ✅ done | 14 | — | Поддерживать без регрессий | `pyinstaller --clean botik.spec` успешен; dist/botik.exe 63 МБ |
| 13 | OHLCV + data workers | ✅ done | F1 | 5, 6, 7, 14, R1, R2 | Использовать `data_runner` для bootstrap и проверки данных | Реализованы `ohlcv_worker.py` и `data_runner.py`; исторический blocker снят |
| 14 | Preflight check (DB, API, config, модели, Telegram) | ✅ done | — | 12 | Поддерживать без регрессий | 9/12 проверок OK; 2 IMPORTANT warn — API ключи и Telegram не в `.env` (ожидаемо для paper-режима); все ML модели найдены v2 |
| 15 | Дашборд: вкладка Состояние системы | ✅ done | F2 | — | Поддерживать live-статус процессов, диагностику и ошибки | `get_system_status()` + `_loadOpsPage()`: процессы, .env, диагностика, статистика БД, последние ошибки |
| 16 | Telegram: согласование DB-запросов с domain schema | ✅ done | F1 | 3, 14 | Поддерживать `/orders` и `/futures` на introspection-ридерах, устойчивых к варианту схемы | Codex 2026-03-21: `/orders` и `/futures` теперь читают актуальные поля и переживают варианты `size/unrealised_pnl` и `qty/unrealized_pnl` |

---

## Blockers

| ID блокера | Какие шаги затронуты | Статус | Что блокирует | Что нужно для снятия | Краткая причина |
|------------|----------------------|--------|----------------|----------------------|-----------------|
| BLOCKER-1 | 5, 6, 7, R1, R2 | ✅ снят | Исторически блокировал отсутствие данных в `price_history` | Шаг 13 уже выполнен; теперь нужно использовать результат в R1 и R2 | Блокировка была снята после добавления `ohlcv_worker.py` и `data_runner.py` |
| BLOCKER-2 | 5, 6, 7, 14, 12 | 🔒 active | Незавершённые возвраты R1-R4 не дают закрыть ML-контур и preflight | Выполнить R1, R2, затем R3 и R4, после чего обновить статусы шагов 5, 6 и 7 | Ранние шаги уже написаны, но не подтверждены на реальных данных и runtime wiring |
| BLOCKER-3 | 6, R5 | 🔒 active | Финальная проверка demo API для spot runtime не доведена до конца | Выполнить R5 после подтверждения рабочих demo API ключей и окружения | Спот-runtime нельзя считать полностью проверенным без возврата к demo API и REST poller |
| BLOCKER-4 | 11, R7 | ✅ снят | PostgreSQL 18 установлен напрямую на Windows без Docker | R7 выполнен 2026-03-21 | — |

- Полный цикл данных для снятия хвостов по шагам 5-7: `python -m src.botik.runners.data_runner`
- Быстрый прогон данных без bootstrap: `python -m src.botik.runners.data_runner --once --skip-bootstrap`

---

## Decision log

| Дата | Тип | Решение или событие | Последствие |
|------|-----|---------------------|-------------|
| 2026-03-21 | architecture | Demo trading выбран вместо testnet | Используются реальные рыночные цены вместо синтетических |
| 2026-03-21 | architecture | REST polling выбран вместо private WebSocket | Решение совместимо с ограничениями Bybit demo |
| 2026-03-21 | architecture | Зафиксирована схема из трёх моделей: Historian + Predictor + OutcomeLearner | ML-контур разделён на исторические паттерны, вход и адаптацию порогов |
| 2026-03-21 | architecture | Зафиксирован Knowledge Warehouse: `RAW → Features → Labels → Weights` | Переобучение можно запускать с нуля из raw-данных |
| 2026-03-21 | architecture | `PositionSizer` использует `risk_qty`, а `kelly_qty` включается только при `is_trained=True` | Kelly-подход не применяется без накопленной статистики |
| 2026-03-21 | architecture | `PositionPolicy` оставлен как точка расширения (`SimpleExit → PartialExit → Averaging → Hedge`) | Движок можно расширять без переписывания базового runtime |
| 2026-03-21 | dependency | Шаг 6 был начат до шага 13 и переведён в `partial` | Создана обязательная очередь возвратов R1-R5, чтобы не потерять поздние зависимости |
| 2026-03-21 | training | Для `labeled_samples` приняты веса: исторические `1.0`, live trades `3.0` | Дообучение не должно вытеснять исторический сигнал |
| 2026-03-21 | bugfix | BUG-1: timeout в `futures_paper.py:on_price_tick` опирается на время открытия из БД, а не на текущее время | Таймаут снова считается корректно для уже открытых позиций |
| 2026-03-21 | bugfix | BUG-2: `.env` загружается в `os.environ` для runner-ов через `load_dotenv()` | Runners видят переменные окружения из файла без ручного экспорта |
| 2026-03-21 | bugfix | BUG-3: для `futures_protection_orders` зафиксированы `UNIQUE(symbol, side)` и UPSERT | Убраны дубли и декартово произведение в JOIN |
| 2026-03-21 | process | Codex реструктурировал `WORKPLAN.md` и вынес правила агента в `CLAUDE.md` | План стал обязательным динамическим протоколом с `Active plan`, `Blockers`, `Decision log` и `Resume queue` |
| 2026-03-21 | bugfix | Во `webview`-дашборде чтение `futures_positions` опиралось на несуществующий столбец `status`; источник переведён на `protection_status`, а snapshot теперь считает реальные futures summary-метрики | Вкладка `Фьючерсы` снова может показывать живые позиции и суммарный `unrealised_pnl` |
| 2026-03-21 | bugfix | `webview`-ридер `futures_positions` дополнительно переведён на introspection схемы, потому что в проекте встречаются оба варианта полей: `size/unrealised_pnl` и `qty/unrealized_pnl` | Вкладка `Фьючерсы` стала устойчивой к переходным версиям schema, а не только к одному варианту таблицы |
| 2026-03-21 | verification | В рабочем дереве отсутствует `data/stats.db`, поэтому live-проверка вкладки `Фьючерсы` против реальной базы была недоступна | Проверка выполнена через `py_compile` и временную SQLite-схему с `futures_positions`; при появлении рабочей БД стоит быстро перепроверить UI в живом режиме |
| 2026-03-21 | bugfix | Во `webview`-дашборде `spot`-вкладка читала legacy-поля `side/qty/entry_price/status`, которых больше нет в актуальной `spot_holdings`; страница переведена на live summary и на отдельные выборки `positions / orders / fills` | Вкладка `Спот` снова согласована с текущей schema и может показывать реальные holdings, ордера и историю |
| 2026-03-21 | dependency | В `telegram_bot.py` команды `/orders` и `/futures` всё ещё читают legacy-поля из `spot_holdings` и `futures_positions` | Шаг 3 переведён в `partial`; добавлен отдельный шаг 16 и возврат R6, чтобы исправление не потерялось |
| 2026-03-21 | bugfix | В `telegram_bot.py` команды `/orders` и `/futures` переведены на schema-aware выборки с introspection полей вместо legacy SQL по старым колонкам | Шаг 16 закрыт, а шаг 3 возвращён в `done`; Telegram-ответы снова согласованы с domain-таблицами |
| 2026-03-21 | verification | Прямой runtime-импорт `telegram_bot.py` в текущем окружении не проходит без пакета `telebot` | Верификация логики сделана через `py_compile` и smoke-test со stub-модулем `telebot`; при наличии зависимости стоит один раз прогнать живой импорт |
| 2026-03-21 | dependency | При старте шага 10 обнаружено расхождение схемы model registry: `webview_app.py:get_models()` всё ещё опирается на legacy-колонки `model_name/model_type/symbol`, тогда как миграции и `active_models.yaml` живут в другой модели данных | Шаг 10 переведён в `active`; вкладку `Модели` нужно делать через schema-aware агрегацию `active_models.yaml`, `ml_training_runs` и `model_stats`, а не через один legacy SELECT |
| 2026-03-21 | bugfix | Вкладка `Модели` в `webview`-дашборде переведена на schema-aware read model: manifest из `active_models.yaml`, история из `ml_training_runs`, метрики из `model_stats`; `_read_ml_training_status()` больше не читает несуществующие training-колонки из `model_stats` | Дашборд теперь показывает живой статус bootstrap, обучения и готовности моделей даже при переходных вариантах schema model registry |
| 2026-03-21 | verification | Для шага 10 прогнаны smoke-тесты read model на двух вариантах схемы: современный `model_stats(model_id, model_scope, ...)` и legacy-вариант `model_stats(model_name, model_scope, ...)`, плюс отдельная проверка `py_compile` для `webview_app.py` | Подтверждено, что вкладка `Модели` и home-summary `ml_training` переживают как актуальную, так и переходную schema без возврата к заглушкам |
| 2026-03-21 | dependency | При старте шага 11 подтверждено, что `src/botik/storage/db.py` уже умеет работать с PostgreSQL через `DB_URL`, а `psycopg2` установлен, но в окружении отсутствует сама команда `docker` | Шаг 11 переведён в `partial`; добавлен blocker `BLOCKER-4` и возврат `R7`, чтобы не потерять обязательный живой smoke-test миграций на PostgreSQL |
| 2026-03-21 | process | Для шага 11 добавлены `docker-compose.postgres.yml` и `tools/postgres_migration_smoke.py`, чтобы живой smoke-test PostgreSQL миграций сводился к короткому воспроизводимому сценарию | При появлении `docker` останется поднять контейнер и выполнить один целевой прогон по `DB_URL=postgresql://...`, не собирая команды заново |
| 2026-03-21 | verification | Подготовительная часть шага 11 проверена без Docker: `docker-compose.postgres.yml` успешно парсится через YAML, `tools/postgres_migration_smoke.py --help` работает, а пробный запуск с `--wait-sec 0` честно падает с `connection refused` на `127.0.0.1:54329` | Partial по шагу 11 теперь связан только с отсутствием внешнего PostgreSQL-рантайма, а не с ошибкой в compose-файле или smoke-runner |
| 2026-03-21 | implementation | PostgreSQL 18 установлен на Windows напрямую (без Docker); `db.py` дополнен функцией `_sqlite_to_pg()` которая транслирует SQLite-DDL в PostgreSQL-диалект (`AUTOINCREMENT→BIGSERIAL`, `REAL→DOUBLE PRECISION`, `INTEGER→BIGINT`, `INSERT OR IGNORE→ON CONFLICT DO NOTHING`) | Smoke-test прошёл: 10 миграций применены, все required_tables созданы; `DB_URL=postgresql://botik:botik123@localhost:5432/botik` |
| 2026-03-22 | implementation | M3 ProcessManager: `training_worker.py` (subprocess entry point) + `process_manager.py`; 15 тестов OK; `_deploy_if_ready` сохраняет обе модели если accuracy≥0.52 (M3.1); `_update_labeling_registry` обновляет SymbolLabelingRegistry после обучения (M3.2); `_write_log` пишет в app_logs channel=ml_<scope>; `_write_run_status` upsert в ml_training_runs; M4+M5+M6 разблокированы |
| 2026-03-22 | implementation | M6 Dashboard Training Controls: `start_training_scope(scope)` + `stop_training_scope(scope)` в TradingMixin; `_ml_futures_process` + `_ml_spot_process` в webview_app; `_get_data_readiness()` — порог ≥100 candles (MAX по scope); HTML карточка "Управление обучением" с Start/Stop per scope; JS `_applyTrainingControls()`, `apiStartTrainingScope()`, `apiStopTrainingScope()`; 6 новых тестов; 299 тестов OK; v0.0.38 |
| 2026-03-22 | implementation | M5 Dashboard Model Cards UI: `_build_per_model_card()` (state logic: active/ready/training/idle/missing, outcome — только по файлу); `get_model_cards()` (6 карточек historian/predictor/outcome × futures/spot); `get_model_logs(scope)`; HTML: секция "Детали по моделям" (3-кол грид) + ML Логи панель с Futures/Spot переключателем; 14 тестов OK; 293 тестов OK; v0.0.37 |
| 2026-03-22 | implementation | M4 Dashboard Data Layer UI: `backfill_entry.py` + `live_entry.py` (subprocess entry points); `api_data_mixin.py` (get_data_status, start/stop backfill, start/stop live); 12 тестов OK; nav item "Данные" + page-data в HTML; _loadDataPage() + кнопки управления; 279 тестов OK; v0.0.36 |
| 2026-03-22 | bugfix | M2 TrainingPipeline: `_read_candles()` заменена на `_read_candles_chunk()` с LIMIT/OFFSET пагинацией; чанк=10K строк, хвост=29 свечей (_TAIL_SIZE=MIN_CANDLES+FORWARD_CANDLES-1); граничные позиции не теряются; пиковая память O(CHUNK_SIZE) вместо O(всей_истории); тест `test_chunked_reading_produces_same_result_as_full` добавлен |
| 2026-03-22 | dependency | M2 TrainingPipeline не сохраняет модели (нет ModelRegistry.save()) и не обновляет SymbolLabelingRegistry — это ответственность M3; добавлены подзадачи M3.1 и M3.2 |
| 2026-03-22 | implementation | M2 TrainingPipeline: `src/botik/data/training_pipeline.py`; 15 тестов OK; один проход price_history → фичи в памяти → `historian.fit()` + `predictor.fit()`; `_compute_label` — 0.8% вверх=1, -0.6% вниз=0, иначе None; labeled_samples не используется; M3 (ProcessManager) разблокирован |
| 2026-03-22 | implementation | M1.4 LiveDataWorker: `_CategoryKlineWS` + `LiveDataWorker` в `src/botik/data/live_data_worker.py`; 16 тестов OK; `_parse_candle_row` — парсит WS kline dict → tuple, отклоняет невалидные данные; `on_connected`/`on_disconnected` обновляют ws_active в registry; `_stats_loop` каждые 60с обновляет candle_count | M1 (сбор данных) полностью закрыт; M2 (TrainingPipeline) разблокирован |
| 2026-03-22 | refactor | `webview_app.py` (1849 строк) разбит на 8 модулей: `api_helpers`, `api_db_mixin`, `api_models_mixin`, `api_spot_mixin`, `api_futures_mixin`, `api_system_mixin`, `api_settings_mixin`, `api_trading_mixin`; `webview_app.py` стал тонкой точкой входа (~200 строк); 186 тестов OK | Код логически изолирован по ответственности, зависимости явные, поддерживать проще |
| 2026-03-21 | bugfix | `trainer.bootstrap()` использовал `limit_per_symbol=2000` — лабелер получал только 20 образцов из 43k свечей. Поднято до 40000 | Bootstrap стал генерировать 2244 futures / 2023 spot образцов, достаточно для обучения |
| 2026-03-21 | bugfix | `registry._write_db` INSERT в `model_stats` использовал колонку `model_name` (не существует), что откатывало весь transaction вместе с записью в `ml_training_runs` | Исправлено на `model_id`; `ml_training_runs` теперь содержит 4 записи (futures+spot, v1+v2) |
| 2026-03-21 | bugfix | `registry._get_latest_version` использовал LIKE-паттерн `futures_historian_%` по колонке `model_version` которая хранит `v1`, `v2` — никогда не совпадало | Переписан: сначала glob по файлам на диске (надёжно), затем fallback в БД |
| 2026-03-21 | implementation | `tools/preflight.py` переписан с нуля: пять секций (DB, ENV, DATA, ML, API+Telegram), три уровня (REQUIRED / IMPORTANT / INFO), цветной вывод, `--json`, exit code 0/1/2 | Шаг 14 переведён в `partial`; ML-секция показывает корректный статус «не обучена» до bootstrap (R1–R4), остальные проверки полностью работоспособны |
| 2026-03-22 | bugfix | Subprocess из exe: `sys.executable -m ...` не работает в frozen mode (`botik.exe -m ...` — нераспознанный флаг); добавлен `_build_subprocess_cmd(worker)` в `api_helpers.py` + `--worker backfill\|live\|training` dispatch в `windows_entry.py` с `parse_known_args()` для прозрачной передачи флагов | Все воркеры корректно запускаются из exe; subprocess кнопки в Data/Training tabs работают |
| 2026-03-22 | bugfix | BackfillWorker сразу завершался без ошибок — symbol_registry был пустой, `get_needing_backfill()` возвращал пустой список | Добавлена кнопка "Загрузить все монеты с Bybit" вызывающая `seed_symbol_registry()` |
| 2026-03-22 | implementation | `seed_symbol_registry()` заменён с hardcoded 5 символов на полное discovery через Bybit public API: fetch_linear_instruments (USDT perpetuals ~300-400) + fetch_spot_instruments (USDT pairs ~400-600); × 4 интервала = ~2800-4000 строк; всегда использует api.bybit.com (не demo); v0.0.43 | BackfillWorker получает полный список монет для прогрессивного скачивания данных |
| 2026-03-22 | implementation | `symbol_universe.py` расширен: добавлены `LinearInstrument` dataclass, `fetch_linear_instruments()`, `filter_linear_symbols()` (USDT perpetuals, contractType=LinearPerpetual, status=Trading) | Унифицированный модуль для получения торговой вселенной Bybit по любой категории |
| 2026-03-22 | cleanup | Старые данные в ml_training_runs и model_stats (из bootstrap) удалены однократно из data/botik.db и dist/data/botik.db; кнопка "Очистить историю обучения" удалена из UI | Дашборд стартует с чистой историей без артефактов от старого кода |
| 2026-03-22 | localization | Вкладка Модели: модели переведены в русские имена (Историк/Предиктор/Outcome-обучение); scope_label → Фьючерсы/Спот; ML log tabs → Фьючерсы/Спот; training controls → Старт/Стоп | UI полностью русифицирован, нет смешения языков |
| 2026-03-22 | implementation | T29 WebSocket real-time цены: `api_ticker_mixin.py` — TickerMixin; фоновый daemon-поток; asyncio WS на `tickers.*` (linear); delta-мерж; stale=30s; 13 тестов; `dashboard_preview.html` — `_pollTickers()` каждые 3с, `_renderTickerRow()`, stale-индикаторы; Bybit WS подтверждён (BTCUSDT $68825); 312 тестов OK; v0.0.45; exe 70 МБ |
| 2026-04-06 | implementation | T32 Бэктестинг: `src/botik/backtest/` — `_BaseBacktestRunner`, `FuturesBacktestRunner`, `SpotBacktestRunner`; in-memory позиции (не пишет в БД); спайк-детекция по OHLCV; `BacktestResult` с drawdown/Sharpe/profit_factor; `api_backtest_mixin.py`; страница "Бэктест" с формой, метриками и таблицей сделок; 13 тестов OK |
| 2026-04-06 | implementation | T34 Мульти-символ: добавлены `FUTURES_SYMBOLS` и `SPOT_SYMBOLS` в `_SETTINGS_KEYS`; поля ввода в секциях Фьючерсы/Спот страницы Настройки; сохраняются в .env как остальные параметры |
| 2026-04-06 | implementation | T35 CI/CD: `.github/workflows/windows-package.yml` читает `VERSION` через PowerShell, передаёт `/DMyAppVersion` в ISCC; `installer.iss` использует `#ifndef MyAppVersion` как fallback; артефакты именуются с версией; GitHub Release создаётся автоматически на push тега `v*`; v0.0.49 |
| 2026-04-07 | implementation | T36-T39 UX Data/Balance/CMD: прогресс-бары Futures/Spot + "СЕЙЧАС КАЧАЕТСЯ" карточка (backfill_progress в bot_settings) + мини-лог + пайплайн home page + balance poller BalanceMixin + CREATE_NO_WINDOW в обоих местах + раздельные Spot/Futures кнопки управления; v0.0.61 |
| 2026-04-07 | architecture | Предложены следующие улучшения: SSE/EventBus (T40), стакан orderbook (T41), компонентный HTML (T42), расширение таймфреймов (T43); пользователь согласовал все четыре |
| 2026-03-22 | implementation | T27 Страница "Рынок": nav item + `<div id="page-market">` + `<div class="market-grid">` в HTML; `_renderMarketPage()` — glassmorphism price-cards (flash-up/flash-down при смене цены, range-bar H/L, stale-оверлей); `_pollTickers()` теперь вызывает и `_renderMarketPage`; CSS market-grid/price-card/flash keyframes уже в HTML; v0.0.46; exe пересобран |
| 2026-04-18 | implementation | GUI Migration → Tauri+React: удалён весь старый pywebview GUI (src/botik/gui/ — 22 файла, dashboard_preview.html, dashboard_template.html); добавлены страницы Settings + Market + Orderbook + Backtest в новый React-фронтенд; Foundation Health обогащён 4 MetricCard + PipelineStep; windows_entry.py переписан под запуск Tauri exe + app-service subprocess; visual audit 14/14 страниц — heading visible, нет JS-ошибок |
| 2026-04-20 | research | Vision model benchmark: gemma3:4b и llava:7b через Ollama CPU — оба NOT PRACTICAL. RTX 5060 (Blackwell SM_120, compute 12.0) не поддерживается Ollama 0.21.0 cuda_v13 (runner crash = HTTP 502). CPU режим работает но медленно: gemma3:4b = 256.8с на 50 токенов + 409KB base64 изображения. Доп. проблема: Python urllib на Windows читает системный прокси из реестра → 502; фикс: ProxyHandler({}). Вывод: локальные vision-модели нецелесообразны на этой машине до выхода Ollama с поддержкой Blackwell. Текущий vision layer (tests/vision/ через Claude API) — правильный подход. |
| 2026-04-20 | research | Vision GPU re-verification: предыдущий "NOT PRACTICAL" был ошибочным (OLLAMA_LLM_LIBRARY=cpu в user env → CPU-режим). GPU: gemma3:4b = 1.4-4.6s/request, JSON valid 100%, schema 4/4, VRAM 5299 MiB. Классификация изменена на GOOD DEFAULT TOOL. llava:7b: BLOCKED — CLIP projector + Blackwell несовместимость (VRAM не загружается, ExitCode=-1). |
| 2026-04-20 | blocker | 11B model evaluation BLOCKED: Cloudflare R2 (Ollama blob CDN) возвращает SSL handshake failure с этой сети (ISP блокировка подозревается). `registry.ollama.ai` доступен, блоб-сервер — нет. HuggingFace доступен, но все варианты llama3.2-vision:11b — gated (Meta license). Вердикт: gemma3:4b остаётся единственным рабочим локальным инструментом. Разблокировка: VPN прокси (NekoBox HTTPS_PROXY) или ручной импорт через HF token. Задокументировано в docs/testing/NEXT_STEPS.md#VS-6. |
| 2026-04-20 | research | llama3.2-vision:11b скачан и протестирован через NekoBox прокси (127.0.0.1:2080). VRAM: 5.53 GB (умещается). Холодный старт: 45s. Тёплый запрос на реальных скриншотах: 21-118s avg 76s. JSON валидность: 1/3 в бенчмарке (33%). НЕ ПРАКТИЧНО для авто-тестов (10-50× медленнее gemma3:4b, ненадёжный JSON). Можно использовать только как ручной инструмент разового глубокого аудита. gemma3:4b остаётся GOOD DEFAULT TOOL. |
| 2026-04-20 | research | "Agent Eyes" тест: оба модели протестированы на роль визуального наблюдателя (status badges, error banners, nav detection). gemma3:4b: RUNNING/OFFLINE badge 2/2 за 1.4s, error banner 2/3 за 1.4-9.7s. llama3.2-vision:11b: 1/2 badges (неверно определил OFFLINE как RUNNING), 2/3 error за 11-19s, JSON template leakage. ВЫВОД: gemma3:4b — правильный выбор для agent eyes (13× быстрее, точнее). Region crops (400-500px) ускоряют обоих в 6-10× vs full screenshots. Ложный позитив на runtime.png — оба видят красный OFFLINE badge как ошибку, проблема формулировки вопроса. |
| 2026-04-20 | implementation | Vision loop интегрирован в interaction тесты. Создан tests/visual/vision_loop.helpers.ts: analyzeRegion, classifyElementState, detectActionBanner, detectPanelVisibility, compareStates, logVisionResult. Transport: node:http loopback (bypass proxy). 3 сценария: Telegram panel (healthy ✅), Jobs error banner (type=error, text читает ✅), Runtime OFFLINE→RUNNING transition_confirmed ✅. 4/4 тесты pass без vision (6.1s), 4/4 pass с OLLAMA_VISION=1 (18s cold / ~12s warm). Разграничение: status badge ≠ action banner — исключает false-positive паттерн. |

---

## Текущие задачи

| ID | Задача | Статус | Следующее действие |
|----|--------|--------|--------------------|
| T29 | WebSocket real-time цены в дашборд | ✅ done | TickerMixin + _pollTickers; 10 символов live из Bybit WS; v0.0.45 |
| T27 | Страница "Рынок" (glassmorphism price cards) | ✅ done | nav + HTML + JS _renderMarketPage; flash animation; high/low bar; v0.0.46 |
| T33 | Настройки стратегии из UI (SL/TP/риск) | ✅ done | _SETTINGS_KEYS+15 ключей; futures/spot runners читают env; HTML секция "Параметры стратегии"; 304 тестов OK; v0.0.47 |
| T30 | PnL аналитика: equity curve, drawdown, win rate | ✅ done | api_analytics_mixin.py + страница "PnL Аналитика" в HTML; 23 теста; 305 тестов OK; v0.0.48 |
| T32 | Бэктестинг | ✅ done | src/botik/backtest/ (BacktestRunner + BacktestResult); api_backtest_mixin.py; страница "Бэктест" в HTML; 13 тестов; 348 тестов OK; v0.0.50 |
| T34 | Мульти-символ: управление символами из UI | ✅ done | FUTURES_SYMBOLS + SPOT_SYMBOLS в _SETTINGS_KEYS и HTML настройках; v0.0.50 |
| T35 | CI/CD: авто-сборка exe по git push | ✅ done | .github/workflows/windows-package.yml: читает VERSION, передаёт /DMyAppVersion в ISCC, artifact с версией, GitHub Release на тег v*; installer.iss: #ifndef MyAppVersion; v0.0.49 |
| T36 | UX: видимость сбора данных (Data tab) | ✅ done | v0.0.61 — прогресс-бары Futures/Spot, карточка "СЕЙЧАС КАЧАЕТСЯ" (symbol+TF+N/total), мини-лог с auto-scroll, пайплайн-карточка на home |
| T37 | Balance poller (Bybit demo REST) | ✅ done | api_balance_mixin.py: daemon-поток, hmac-подпись, INSERT в account_snapshots каждые 30с; баланс 428k USDT отображается |
| T38 | CMD-окно flashing | ✅ done | CREATE_NO_WINDOW в ManagedProcess.start() и ProcessManager.start_training(); больше нет вспышек консоли |
| T39 | Control panel: раздельные Spot/Futures кнопки | ✅ done | Удалён select-dropdown, добавлены две строки Start/Stop per scope с state-тегами |
| T40 | SSE / EventBus — реактивные обновления | ✅ done | event_bus.py: EventBus + EventDispatcher; evaluate_js push; _onServerEvent в JS; log_entry + balance_update; v0.0.65 |
| T41 | Стакан (order book) — персистентный сбор | ✅ done | api_orderbook_mixin.py: REST-поллер 20с, migration 13 orderbook_snapshots, page-orderbook, 9 тестов; v0.0.65 |
| T42 | Компонентный HTML — разбить dashboard на page-*.html | ✅ done | 13 page-*.html компонентов, dashboard_template.html, assemble_dashboard_html(), /rebuild-html endpoint; v0.0.65 |
| T43 | Таймфреймы backfill — добавить 4h/D/W в конфиг | ✅ done | data.backfill_intervals в config.example.yaml (1/5/15/60/240/D/W); backfill_entry.py + api_data_mixin читают из конфига; v0.0.65 |
| W1 | Редизайн HTML (glassmorphism) | ⬜ waiting | Опционально — после M0-M6 |
| W3 | Рефакторинг webview_app.py → 8 модулей | ✅ done | Разбито на api_helpers, api_db_mixin, api_models_mixin, api_spot_mixin, api_futures_mixin, api_system_mixin, api_settings_mixin, api_trading_mixin; 186 тестов OK |
| W2 | Пересборка exe — bundled_file + html= фикс | ✅ done | 68 МБ |
| P1 | API bridge: polling fallback вместо только pywebviewready | ✅ done | Python-side bootstrap: _bootstrap_js() ждёт bridge и вызывает _initAPI(); exe подтверждён — get_snapshot каждые 2с |
| P2 | Настройки: auto-load при открытии после API connect | ✅ done | ROOT_DIR найден динамически (ищет .env/config.yaml вверх от exe); _ENV_ALIASES для BYBIT_API_SECRET; status-индикаторы "✓ задан" в UI |
| P3 | Спот: кнопки продажи монет + "Продать всё → USDT" | ✅ done | sell_spot_position() + sell_all_spot() в Python API; кнопки в таблице позиций |
| P4 | Фьючерсы: закрытие позиции, изменение TP/SL | ✅ done | close_futures_position() + update_futures_tp_sl() в Python API; кнопка "Закрыть" в futures таблице |
| P5 | Модели: кликабельные карточки, история, win rate | ✅ done | onclick открывает оверлей с историей runs, win rate, метриками по scope |
| P6 | Система: RAM, CPU, DB-пинг, время процессов | ✅ done | psutil добавлен; ram/cpu/db_ping в get_system_status(); прогресс-бары в ops-странице |
| P7 | Версия/обновления: вывод в UI | ✅ done | topbar-version обновляется из get_snapshot(); ops-version строка |

---

## ML Training System — Фаза M (текущий приоритет)

> Цель: Разделить сбор данных / обучение / трейдинг на независимые слои.
> Слои общаются ТОЛЬКО через БД. Никакого прямого вызова между слоями.

### Архитектурные решения — зафиксировано 2026-03-22

| Решение | Итог обсуждения |
|---|---|
| labeled_samples как промежуточный слой | ❌ ОТМЕНЁН — двойная работа, данные лежат мёртвым грузом |
| Единый проход обучения | ✅ price_history → фичи в памяти → обучение за ОДИН проход по истории |
| labeled_samples остаётся для | ✅ только live trade feedback (OutcomeLearner, weight=3.0) |
| Хранение price_history | ✅ PostgreSQL tablespace ts_market на I: (HDD 931GB) — физически отдельно от app state |
| App state (trades/registry/logs) | ✅ PostgreSQL на C: (NVMe) — быстрый диск для торговой логики |
| Таймфреймы | ✅ 1m + 5m + 15m + 1h — причинно-следственный контекст (≈9GB для 20 символов × 6 лет) |
| Выбор символов | ✅ НЕ топ по ликвидности — разнообразие рыночных режимов (BTC/ETH/SOL/XRP и алты) |
| Глубина истории | ✅ Максимально доступная (BTCUSDT с 2020-03-25, остальные с 2021+) |
| REST /v5/market/kline | ✅ Протестирован: 1000 свечей/запрос, все поля строки, порядок убывания |
| WS kline.1.BTCUSDT | ✅ Протестирован: поле confirm=true только для закрытых свечей — только их сохраняем |
| M0 schema верификация | ✅ price_history колонки совпадают с форматом REST и WS |

### Что нужно сделать вручную (однократно, перед запуском сбора):
1. Создать папку `I:\botik_market`
2. В `psql -U postgres`: `CREATE TABLESPACE ts_market LOCATION 'I:/botik_market'; GRANT CREATE ON TABLESPACE ts_market TO botik;`
3. Запустить миграцию (пересоздаст price_history в tablespace ts_market)

### Граф зависимостей (пересмотрен)
```
M0 (Symbol Registry)
 └─► M1 (BackfillWorker + LiveDataWorker)  — наполняет price_history
      └─► M2 (TrainingPipeline)            — один проход: price_history → обучение
           └─► M3 (ProcessManager)         — subprocess + логи + статусы
                └─► M5 (Dashboard Cards)
                     └─► M6 (Dashboard Controls)
M0+M1 ──────────────► M4 (Dashboard: Data Layer UI)
```

### Правило: не начинать задачу M(N) пока M(N-1) не имеет статус ✅ done

| ID | Задача | Слой | Статус | Зависит от | Разблокирует |
|----|--------|------|--------|------------|--------------|
| M0 | **Symbol Registry**: `symbol_registry` + `symbol_labeling_status`. Без хардкода символов. 24 теста | БД | ✅ done | — | M1, M4 |
| M1.0 | **REST API тест**: реальный вызов Bybit /v5/market/kline, формат подтверждён | Исследование | ✅ done | — | M1.1 |
| M1.1 | **WS kline тест**: подключение к stream.bybit.com, поле confirm верифицировано | Исследование | ✅ done | — | M1.2 |
| M1.2 | **Глубина истории**: BTCUSDT с 2020-03-25, ~119 bytes/свеча, 9GB для 20 символов × 4 TF × 6 лет | Исследование | ✅ done | — | M1.3 |
| M1.3 | **BackfillWorker**: читает SymbolRegistry → качает историю по REST → обновляет candle_count | Сбор данных | ✅ done | M0 | M1.4, M2 |
| M1.4 | **LiveDataWorker**: WebSocket kline подписка → подтверждённые свечи → обновляет ws_active | Сбор данных | ✅ done | M1.3 | M2, M4 |
| M2 | **TrainingPipeline**: один проход по price_history чанками → фичи в памяти → обучение (no labeled_samples) | Обучение | ✅ done | M1.3 | M3 |
| M3 | **ProcessManager**: subprocess per scope, логи в app_logs channel=ml_<scope>_<model>, статусы в ml_training_runs | Обучение | ✅ done | M2 | M5, M6 |
| M3.1 | **Model saving**: после fit() сохранять модели через ModelRegistry.save() | Обучение | ✅ done | M3 | M5 |
| M3.2 | **SymbolLabelingRegistry update**: после обучения символа вызывать set_status(..., "ready", labeled_count) | Обучение | ✅ done | M3 | M4 |
| M4 | **Dashboard: Data Layer UI**: таблица символов, candle_count, WS-статус, Start/Stop | UI | ✅ done | M0+M1.3 | M6 |
| M5 | **Dashboard: Model Cards UI**: 6 карточек с описанием, статусом, per-model логами | UI | ✅ done | M3 | M6 |
| M6 | **Dashboard: Training Controls**: Start/Stop per model, блокировка без данных | UI | ✅ done | M3+M4+M5 | — |

---

## Resume queue

| ID | Вернуться к | После чего | Что проверить при возврате | Причина | Статус |
|----|-------------|------------|----------------------------|---------|--------|
| R1 | Шаг 5 | ✅ выполнено 2026-03-21 | `ModelTrainer.bootstrap(scope="futures")` завершён: hist=0.681 pred=0.710 v2, 2244 образцов | Закрыт | ✅ done |
| R2 | Шаги 6 и 7 | ✅ выполнено 2026-03-21 | `ModelTrainer.bootstrap(scope="spot")` завершён: hist=0.689 pred=0.721 v2, 2023 образцов | Закрыт | ✅ done |
| R3 | Шаг 5 | ✅ выполнено 2026-03-21 | `predict_fn` подключена в `FuturesRunner.__init__` строки 101–105; обновляется при incremental retrain строка 225 | Закрыт | ✅ done |
| R4 | Шаг 7 | ✅ выполнено 2026-03-21 | `_predict_fn` активен в `SpotRunner.__init__` строки 121–128, применяется в `_on_orderbook` строки 321–334 | Закрыт | ✅ done |
| R5 | Шаг 6 | ✅ выполнено 2026-03-21 | `RestPrivatePoller` читает ключи из env; при отсутствии ключей корректно переходит в offline (строка 98–102); wiring верифицирован | Закрыт | ✅ done |
| R7 | Шаг 11 | ✅ выполнено 2026-03-21 | PostgreSQL 18 установлен напрямую без Docker; `db.py` дополнен `_sqlite_to_pg()`; smoke-test прошёл: 10 миграций, все required_tables присутствуют | Закрыт | ✅ done |
