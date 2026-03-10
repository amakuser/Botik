# PROD Runbook

## 1. Режимы запуска

- Linux/server (headless): `python -m src.botik.main --config config.yaml`
- Windows desktop GUI: `python -m src.botik.gui.app`
- Windows packaged executable: `botik.exe` (entry: `src/botik/windows_entry.py`)

Важно: пользовательский desktop-flow — одно главное окно GUI, без запуска множества runtime окон.

## 2. Подготовка сервера

1. Клонировать репозиторий в `/opt/Botik`.
2. Создать `.env` и `config.yaml`.
3. Создать venv и установить зависимости:
   - `python3 -m venv .venv`
   - `. .venv/bin/activate`
   - `pip install -r requirements.txt`

## 3. Systemd deployment

1. Установка unit-файлов:
   - `sudo bash /opt/Botik/deploy/install_systemd.sh /opt/Botik`
2. Запуск:
   - `sudo systemctl start botik-trading.service`
   - `sudo systemctl start botik-ml.service`
3. Проверка:
   - `systemctl status botik-trading.service`
   - `systemctl status botik-ml.service`

## 4. Runtime последовательность (оператор)

При старте runtime:
1. Инициализация config/storage.
2. Reconciliation startup run (если capability поддерживается executor).
3. Запуск strategy loop.
4. Периодический reconciliation loop по интервалу.
5. Параллельные записи в legacy + domain tables.

## 5. Reconciliation: как читать статус

Проверка в БД:
- `reconciliation_runs` — последние запуски и summary.
- `reconciliation_issues` — открытые конфликты.
- `events_audit` — журнал ключевых событий.

Критично:
- при открытых issue типов `orphaned_exchange_*` / `local_*_missing_on_exchange`
  новые entry по symbol блокируются (symbol-level lock).

## 6. Futures protection lifecycle

Ожидаемый flow:
- entry -> `pending` (или `repairing` при повторной попытке),
- apply `set_trading_stop`,
- verify через `get_positions`,
- итоговый статус: `protected` либо `unprotected/failed`.

Новые entry по symbol запрещены, если статус в:
- `pending`
- `repairing`
- `failed`
- `unprotected`

## 7. Paper mode ограничения

Paper mode полезен для отладки loop/GUI, но:
- reconciliation capability = unsupported,
- futures protection capability = unsupported.

Это не ошибка конфигурации production, это ожидаемое ограничение режима.
Runtime должен явно логировать unsupported status и не выдавать ложный “protected/reconciled”.

## 8. Обновление версии

```bash
sudo bash /opt/Botik/deploy/update.sh /opt/Botik master
```

Скрипт делает:
1. `git pull --ff-only`
2. обновление зависимостей
3. тесты
4. preflight
5. restart сервисов

## 9. Быстрая диагностика

1. `python tools/preflight.py --config config.yaml`
2. `python bybit_smoke_test.py --symbol BTCUSDT --ws-samples 3`
3. Логи:
   - `journalctl -u botik-trading.service -n 100 --no-pager`
   - `journalctl -u botik-ml.service -n 100 --no-pager`
4. Проверка reconciliation/protection в БД:
   - `sqlite3 data/botik.db "select trigger_source,status,started_at_utc from reconciliation_runs order by started_at_utc desc limit 10;"`
   - `sqlite3 data/botik.db "select issue_type,symbol,status,created_at_utc from reconciliation_issues where status='open' order by created_at_utc desc limit 20;"`
   - `sqlite3 data/botik.db "select symbol,side,protection_status,updated_at_utc from futures_positions order by updated_at_utc desc limit 20;"`
