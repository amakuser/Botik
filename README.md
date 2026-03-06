# Bybit Spot DEMO Bot + ML Service

Торговый бот для **демо-счёта Bybit Spot** (api-demo.bybit.com) и отдельный ML-сервис. Код на английском, комментарии и документация — на русском (удобно для обучения).

## Что это

- Бот выставляет и снимает ордера на **DEMO**, считает PnL по сделкам (fills).
- Стратегия: микро-спред маркет-мейкинг (0–2 post-only лимита на инструмент).
- Все ордера проходят через **RiskManager** (жёсткие лимиты).
- **ML-сервис** работает отдельным процессом: аналитика и обучение по архиву без нагрузки на торговый цикл.

## Установка

1. **Python 3.11+**
2. Установка зависимостей (когда появится `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```
3. Скопировать пример переменных окружения и заполнить секреты:
   ```bash
   copy .env.example .env
   ```
   В `.env` указать: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BYBIT_API_KEY` и один из вариантов подписи: `BYBIT_API_SECRET_KEY` (HMAC, основной) или `BYBIT_RSA_PRIVATE_KEY_PATH` (RSA, fallback). Для обратной совместимости поддерживается `BYBIT_API_SECRET`. Файл `.env` в репозиторий **не коммитить**.

## Запуск

- **Торговый бот** (маркетдата, стратегия, RiskManager, execution, Telegram):
  ```bash
  python -m src.botik.main
  ```
  Опционально: `--config путь/к/config.yaml`. Секреты и символы — из `.env` и конфига.
- **ML-сервис** (отдельный процесс, онлайн-аналитика и обучение по расписанию):
  ```bash
  python -m ml_service.run_loop --config config.yaml
  ```
  Режимы:
  - bootstrap (сбор статистики + автокалибровка): `python -m ml_service.run_loop --mode bootstrap`
  - train (обучение lifecycle-модели): `python -m ml_service.run_loop --mode train --train-once`
  - predict (скоринг последних сигналов активной моделью): `python -m ml_service.run_loop --mode predict --predict-once`
- **Экспорт lifecycle-датасета для ML** (одна строка = один `signal_id`):
  ```bash
  python tools/export_trade_dataset.py --db-path data/botik.db --out-csv data/ml/trades_dataset.csv
  ```
  Опционально Parquet:
  ```bash
  python tools/export_trade_dataset.py --db-path data/botik.db --out-csv data/ml/trades_dataset.csv --out-parquet data/ml/trades_dataset.parquet
  ```
- Старый скрипт Telegram: `python PythonBot_Telegram.py` — требует `TELEGRAM_BOT_TOKEN` в `.env`.

## Версия приложения

- Текущая версия хранится в файле `VERSION`:
  - `version=1.0.0`
  - `build=1`
- Показать текущую версию:
  ```bash
  python tools/version_bump.py --show
  ```
- Увеличить только счётчик сборки:
  ```bash
  python tools/version_bump.py --increment 1
  ```
- Поставить новую базовую версию и сбросить счётчик:
  ```bash
  python tools/version_bump.py --set-version 1.1.0 --reset-build --increment 1
  ```
- GUI и Telegram supervisor показывают версию в статусе.

### Режимы запуска

- **Windows GUI (локально):**
  - `run_windows_gui.bat`
  - или `python -m src.botik.gui.app`
  - в GUI есть:
    - Start/Stop для trading и ML
    - Preflight
    - live-лог
    - LED-статусы `RUNNING / STOPPED / ERROR`
    - Copy/Copy All для логов
    - вкладка `Settings` для редактирования `.env` и `config.yaml` прямо в окне
    - изменения в Settings сохраняются автоматически (auto-save)
- **Linux/server CLI (headless):**
  - `bash run_server_cli.sh config.yaml`
  - или `python -m src.botik.main --config config.yaml`

## Локальное обучение на данных сервера

Сценарий: сервер копит `data/botik.db`, ты обучаешь локально, затем отправляешь модель обратно на сервер и активируешь её.

Команда:
```bash
python tools/ml_remote_cycle.py --remote-user <user> --remote-host <host> --remote-repo-path /opt/Botik
```

Что делает скрипт:
1. Забирает БД с сервера (`scp`).
2. Запускает локальное обучение (`python -m ml_service.run_loop --train-once`).
3. Отправляет артефакт модели на сервер.
4. Активирует модель на сервере через `tools/promote_model.py`.

Автокалибровка fee/slippage сохраняется в `data/ml/autocalibration.json` после накопления достаточного числа fills.

## Прод-развертывание (Linux, systemd)

В репозитории есть шаблоны:
- `deploy/systemd/botik-trading.service`
- `deploy/systemd/botik-ml.service`
- `deploy/update.sh`

Типовой цикл обновления на сервере:
```bash
sudo bash /opt/Botik/deploy/update.sh /opt/Botik master
```

## Проверка WS и REST

- Public WS для рынка Spot не требует API-ключей. Для данных mainnet используйте `stream.bybit.com`.
- Проверка потока котировок:
  ```bash
  python bybit_smoke_test.py --symbol BTCUSDT
  ```
- Сравнение mainnet и testnet потока:
  ```bash
  python bybit_smoke_test.py --symbol BTCUSDT --compare-host stream-testnet.bybit.com
  ```
- Проверка REST create/cancel ордера на DEMO:
  ```bash
  python bybit_smoke_test.py --symbol BTCUSDT --check-rest-order --rest-host api-demo.bybit.com --auth-mode hmac
  ```
- Создать и оставить ордер открытым для ручной проверки в UI:
  ```bash
  python bybit_smoke_test.py --symbol BTCUSDT --check-rest-order --rest-host api-demo.bybit.com --auth-mode hmac --keep-order-open
  ```
- Создать ордер и очистить его (cancel):
  ```bash
  python bybit_smoke_test.py --symbol BTCUSDT --check-rest-order --rest-host api-demo.bybit.com --auth-mode hmac --cancel-created-order
  ```
- В конце smoke-теста выводится единая строка результата:
  - `SMOKE_RESULT {...}`
  - удобна для runbook и автоматической проверки.

### Runbook диагностики

1. Если `retCode=10002`:
   - проверьте системное время (NTP);
   - клиент делает автосинхронизацию времени с `/v5/market/time` и 1 повтор запроса.
2. Если `retCode=10004`:
   - проверьте соответствие режима подписи и ключей:
   - для HMAC: `BYBIT_API_SECRET_KEY` (или legacy `BYBIT_API_SECRET`);
   - для RSA: `BYBIT_RSA_PRIVATE_KEY_PATH` должен соответствовать публичному ключу в Bybit.

## Безопасность: как включить и остановить торговлю

- **По умолчанию торговля выключена** (`start_paused=true`). Бот не выставляет ордера, пока не разрешено.
- **Включить торговлю:** команда **/resume** в Telegram.
- **Остановить новые ордера:** команда **/pause** — новые ордера не выставляются, текущие можно снять вручную или через **/panic**.
- **Срочная остановка:** команда **/panic** — отмена всех ордеров. Опционально закрытие позиции рыночным ордером только если в конфиге включено `allow_panic_market_close` (по умолчанию выключено).
- Быстрые инструменты в Telegram: `/start` (кнопки), `/status`, `/scanner`, `/pairs`, `/pause`, `/resume`, `/panic`.
- Дополнительные ограничения позиции в конфиге (`strategy`):
  - `stop_loss_pct`
  - `take_profit_pct`
  - `position_hold_timeout_sec`
  - `force_exit_enabled`
  - `force_exit_time_in_force`

## Секреты

- Все ключи и токены хранятся **только в `.env`** (файл в `.gitignore`).
- В репозиторий коммитить **только `.env.example`** (без подставленных значений).

## Документация

- [docs/PLAN.md](docs/PLAN.md) — план проекта и шаги разработки.
- [docs/PROD_RUNBOOK.md](docs/PROD_RUNBOOK.md) — запуск/обновление на сервере.
- [docs/AGENT_PROMPTS.md](docs/AGENT_PROMPTS.md) — подсказки для AI и структура кода.

---

*Как проверить:* после клонирования — скопировать `.env.example` в `.env`, заполнить токен и при необходимости запустить бота.  
*Частые ошибки:* забыть создать `.env` или закоммитить `.env`.  
*Что улучшить позже:* добавить точную команду запуска основного бота после Шага 2.

