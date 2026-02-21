# -*- coding: utf-8 -*-
"""
Правила на основе статистики (Python): дневные лимиты и множитель размера позиции.

Использует stats.storage для дневного PnL и числа сделок; при низком win rate
уменьшает множитель размера позиции для данной стратегии.
"""
import logging
from typing import Any, Tuple

from stats import storage

log = logging.getLogger("RuleEngine")


class RuleEngine:
    """Проверка дневных лимитов и расчёт множителя размера по win rate."""

    def __init__(self, db_path: str, daily_limits: dict[str, Any]) -> None:
        self.db_path = db_path
        self.daily_limits = daily_limits
        self._win_rate_lookback = 50   # сделок для расчёта win rate
        self._min_win_rate = 0.45     # ниже — уменьшаем размер
        self._position_multiplier_min = 0.5

    def can_open_trade(self, symbol: str, strategy_id: str) -> Tuple[bool, str]:
        """Проверить лимиты: макс. убыток за день, макс. прибыль, макс. число сделок. (разрешено, причина)."""
        max_loss = self.daily_limits.get("max_loss")
        max_profit = self.daily_limits.get("max_profit")
        max_trades = self.daily_limits.get("max_trades")

        try:
            today_pnl = storage.get_today_pnl(self.db_path)
            today_count = storage.get_today_trade_count(self.db_path)
        except Exception as e:
            log.warning("RuleEngine storage read: %s", e)
            return True, ""

        if max_loss is not None and today_pnl <= -abs(float(max_loss)):
            return False, f"daily loss limit reached (PnL={today_pnl:.2f})"
        if max_profit is not None and today_pnl >= float(max_profit):
            return False, f"daily profit cap reached (PnL={today_pnl:.2f})"
        if max_trades is not None and today_count >= int(max_trades):
            return False, f"daily trade limit reached ({today_count} trades)"
        return True, ""

    def get_position_size_multiplier(self, strategy_id: str) -> float:
        """Множитель размера позиции 0.5..1.0 по win rate за последние _win_rate_lookback сделок."""
        try:
            trades = storage.get_trades_for_ml(self.db_path, limit=self._win_rate_lookback)
            strategy_trades = [t for t in trades if t.get("strategy_id") == strategy_id]
            if len(strategy_trades) < 20:
                return 1.0
            wins = sum(1 for t in strategy_trades if (t.get("pnl") or 0) > 0)
            rate = wins / len(strategy_trades)
            if rate >= self._min_win_rate:
                return 1.0
            return max(self._position_multiplier_min, rate / self._min_win_rate)
        except Exception as e:
            log.debug("get_position_size_multiplier: %s", e)
            return 1.0
