# PROD Runbook

## 1. Подготовка сервера

1. Клонировать репозиторий в `/opt/Botik`.
2. Создать `.env` и `config.yaml`.
3. Создать venv и установить зависимости:
   - `python3 -m venv .venv`
   - `. .venv/bin/activate`
   - `pip install -r requirements.txt`

## 2. Установка сервисов

1. Выполнить:
   - `sudo bash /opt/Botik/deploy/install_systemd.sh /opt/Botik`
2. Запустить:
   - `sudo systemctl start botik-trading.service`
   - `sudo systemctl start botik-ml.service`
3. Проверить:
   - `systemctl status botik-trading.service`
   - `systemctl status botik-ml.service`

## 3. Обновление версии

Команда:

```bash
sudo bash /opt/Botik/deploy/update.sh /opt/Botik master
```

Что делает:
1. `git pull --ff-only`
2. установка/обновление зависимостей
3. тесты
4. preflight (`tools/preflight.py`)
5. restart сервисов

## 4. Локальное ML-обучение на данных сервера

С локального компьютера:

```bash
python tools/ml_remote_cycle.py --remote-user <user> --remote-host <host> --remote-repo-path /opt/Botik
```

Цикл:
1. копирует `data/botik.db` с сервера;
2. тренирует локально;
3. отправляет артефакт модели на сервер;
4. активирует модель в `model_registry`.

## 5. Быстрая диагностика

1. `python tools/preflight.py --config config.yaml`
2. `python bybit_smoke_test.py --symbol BTCUSDT --ws-samples 3`
3. Проверить логи:
   - `journalctl -u botik-trading.service -n 100 --no-pager`
   - `journalctl -u botik-ml.service -n 100 --no-pager`
