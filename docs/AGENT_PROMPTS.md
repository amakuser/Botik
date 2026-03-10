# AGENT PROMPTS / GUIDELINES (Botik)

## 1. Repo scope

Botik — не spot-only проект. Поддерживаются два торговых домена:
- Spot holdings/orders/fills
- Futures positions/orders/protection

Работай поверх существующего кода, без rewrite.

## 2. Entry points

- Runtime: `src/botik/main.py`
- Desktop GUI: `src/botik/gui/app.py`
- Windows packaged launcher: `src/botik/windows_entry.py`

Single-exe flow должен сохраняться (GUI по умолчанию, `--nogui` опционально).

## 3. Domain model (обязательно учитывать)

### Shared core
- `account_snapshots`
- `reconciliation_runs`
- `reconciliation_issues`
- `strategy_runs`
- `events_audit`

### Spot
- `spot_balances`
- `spot_holdings`
- `spot_orders`
- `spot_fills`
- `spot_position_intents`
- `spot_exit_decisions`

### Futures
- `futures_positions`
- `futures_open_orders`
- `futures_fills`
- `futures_protection_orders`
- `futures_position_decisions`

## 4. Runtime invariants

1. Legacy write-path (`orders`, `fills`) нельзя ломать без причины.
2. Domain writes должны идти параллельно legacy.
3. Reconciliation запускается при старте и по расписанию.
4. Symbol-level reconciliation lock блокирует только новые entry, не read-only refresh.
5. Futures protection не подтверждается только по `retCode`; нужен verify-from-exchange.
6. Block entry по futures symbol при protection status:
   - `pending`
   - `repairing`
   - `failed`
   - `unprotected`

## 5. Paper mode policy

Paper mode — ограниченный режим:
- protection capability unsupported,
- reconciliation capability unsupported.

Нельзя создавать ложное состояние “всё protected/reconciled”.
Нужно явно логировать/отображать unsupported статус.

## 6. Change policy

- Не делать broad refactor без запроса.
- Не удалять schema foundation и launcher flow.
- Не ломать ML pipeline без необходимости.
- Делать маленькие проверяемые этапы с тестами.
- Коммитить атомарно, с понятным сообщением.

## 7. Проверка перед merge

Минимум:
- `pytest -q`
- проверка `git status`
- если менялся runtime wiring, добавить/обновить tests на call-path, а не только helper-level.
