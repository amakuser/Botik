# -*- coding: utf-8 -*-
"""
Стратегия по пересечению скользящих средних (Python).

Long: быстрая MA выше медленной. Short: быстрая ниже медленной.
Средние считаются в SyncExecutor по кэшу свечей (executor передаёт fast_ma/slow_ma в extra).
"""
from typing import Any, Optional

from strategies.base import BaseStrategy, MarketData, Signal


class MAStrategy(BaseStrategy):
    """
    Пересечение MA: long при fast_ma > slow_ma, short при fast_ma < slow_ma.
    Параметры в конфиге: fast_period, slow_period, position_size_pct.
    """

    def on_tick(self, market_data: MarketData) -> Optional[Signal]:
        p = self.get_params()
        fast_period = p.get("fast_period", 10)
        slow_period = p.get("slow_period", 20)
        size_pct = p.get("position_size_pct", 0.02)
        # MA считаются в executor из свечей и кладутся в market_data.extra
        fast_ma = market_data.extra.get("fast_ma")
        slow_ma = market_data.extra.get("slow_ma")
        if fast_ma is None or slow_ma is None:
            return None
        size = market_data.price * size_pct if market_data.price else 0
        if fast_ma > slow_ma:
            return Signal(direction="long", size=size, strategy_id=self.__class__.__name__)
        if fast_ma < slow_ma:
            return Signal(direction="short", size=size, strategy_id=self.__class__.__name__)
        return None
