# Подсказки для AI / агента (Botik)

## Структура проекта

- **Торговый бот:** `src/botik/` — точка входа `main.py`, конфиг `config.py`, маркетдата `marketdata/`, исполнение `execution/`, стратегия `strategy/`, риск `risk/`, состояние `state/`, хранилище `storage/`, управление `control/`, утилиты `utils/`.
- **ML-сервис:** `ml_service/` — отдельный процесс; `features.py`, `dataset.py`, `train.py`, `evaluate.py`, `run_loop.py`.
- **Конфиг:** корень — `config.example.yaml`, `.env.example`. Секреты только в `.env` (не коммитить).
- **Тесты:** `tests/` — например `test_risk_manager_limits.py`, `test_micro_spread_logic.py`.
- **Документация:** `docs/PLAN.md`, `docs/AGENT_PROMPTS.md`.

## Правила кода

- **Секреты:** никогда не коммитить `.env`, ключи, токены. В репо только `.env.example` с пустыми значениями.
- **Ордера:** любой ордер должен проходить **только через RiskManager** (жёсткие лимиты). Прямые вызовы execution в обход RiskManager не допускаются.
- **На диск:** сырой стакан не писать. Писать только агрегаты (metrics), ордера, сделки (fills), PnL.
- **Идентификаторы** в коде — на английском; комментарии и README — на русском.

## Частые места изменений

- Параметры стратегии и риска — `config.py` и `config.example.yaml`.
- Логика лимитов — `src/botik/risk/manager.py`.
- Логика микро-спреда — `src/botik/strategy/micro_spread.py`.
- Команды Telegram — `src/botik/control/telegram_bot.py`.

---

*Как проверить:* после изменений — запуск тестов и бота в DEMO.  
*Частые ошибки:* добавить секрет в конфиг-файл в репо; обойти RiskManager при выставлении ордера.
