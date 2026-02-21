# Привязка проекта к GitHub

Проект готов к выкладке на GitHub: добавлен `.gitignore` (исключены `config/config.yaml`, `data/`, `*.pkl`, кэш Python и т.д.).

## Шаги (коммиты и пуш делаете вы)

### 1. Инициализировать репозиторий (если ещё не сделано)

В корне проекта `bybit_trading_bot` выполните:

```bash
cd C:\Users\far\bybit_trading_bot
git init
```

### 2. Создать репозиторий на GitHub

- Зайдите на [github.com](https://github.com) → **New repository**.
- Имя, например: `bybit-trading-bot`.
- **Не** добавляйте README, .gitignore или лицензию — репозиторий должен быть пустым.
- Нажмите **Create repository**.

### 3. Привязать удалённый репозиторий

Скопируйте URL репозитория (HTTPS или SSH) и выполните (подставьте свой URL):

```bash
git remote add origin https://github.com/ВАШ_ЛОГИН/bybit-trading-bot.git
```

Или для SSH:

```bash
git remote add origin git@github.com:ВАШ_ЛОГИН/bybit-trading-bot.git
```

### 4. Первый коммит и пуш

```bash
git add .
git status
git commit -m "Initial commit: Bybit trading bot with strategies, limits, ML"
git branch -M main
git push -u origin main
```

Дальнейшие изменения:

```bash
git add .
git commit -m "Описание изменений"
git push
```

---

**Важно:** В репозиторий не попадёт `config/config.yaml` (он в `.gitignore`), чтобы не залить ключи API. Для деплоя используйте переменные окружения или создайте конфиг из `config/config.example.yaml`.
