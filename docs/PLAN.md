# PLAN

## Текущий вектор

Проект ведётся как dual-domain торговый runtime без rewrite:
- Spot domain
- Futures domain
- Shared core для аудита/синхронизации

Цель текущей волны — удерживать корректный runtime wiring и операционную прозрачность, не ломая уже внедрённые P0 изменения.

## Что уже закреплено

1. Domain separation в storage:
- shared core таблицы (`account_snapshots`, `reconciliation_runs`, `reconciliation_issues`, `strategy_runs`, `events_audit`)
- spot таблицы (`spot_holdings/orders/fills/intents/exit_decisions`)
- futures таблицы (`futures_positions/open_orders/fills/protection_orders/position_decisions`)

2. Runtime параллельно пишет:
- legacy (`orders`, `fills`)
- domain tables (spot/futures)

3. Reconciliation:
- autostart перед strategy loop
- scheduled loop
- фиксация reconciliation issues + audit
- symbol-level entry lock по критичным mismatch issue

4. Futures protection flow:
- apply trading stop + verify-from-exchange
- статусы: `pending/protected/unprotected/repairing/failed`
- запрет новых entry по symbol при blocking protection status

5. Paper mode safety:
- capability явно отмечаются как unsupported для protection/reconciliation
- runtime не симулирует ложный protected/reconciled статус

## Ближайшие этапы

### Этап A: Documentation consistency
- README и docs должны честно описывать dual-domain runtime.
- Убрать spot-only формулировки и противоречия.

### Этап B: Risk separation end-to-end
- Уточнить runtime decisions для spot и futures путей без broad rewrite.
- Подтвердить тестами, что futures path protection/liquidation-aware.

### Этап C: GUI operator safety/freshness/status
- Добавить индикаторы свежести данных и operational статусы.
- Показать reconciliation status и protection lifecycle явно.
- Отдельно показать unsupported capability в paper mode.

### Этап D: Integration coverage for wiring
- Проверить startup autostart reconciliation.
- Проверить protection verify wiring в runtime path.
- Проверить safety-path paper mode и read-model wiring.

## Принципы изменений

- Без rewrite проекта.
- Без ломки single-exe/launcher flow.
- Без удаления legacy path, пока нужна совместимость.
- Изменения малыми проверяемыми шагами (commit + push на этап).
