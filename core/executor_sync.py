# -*- coding: utf-8 -*-
"""
Синхронный исполнитель (Python): один поток, очередь из WebSocket.

Поток Bybit WS шлёт тикеры в feed() и свечи в feed_klines(). Здесь считаем MA по кэшу
свечей, обогащаем MarketData и вызываем strategy.on_tick() по очереди.
"""
import logging
import queue
from typing import Any, List, Tuple

from strategies.base import BaseStrategy, MarketData

from core.executor import BaseExecutor

log = logging.getLogger("SyncExecutor")


def _compute_ma(closes: List[float], period: int) -> float | None:
    """Скользящая средняя по последним period ценам закрытия."""
    if not closes or len(closes) < period:
        return None
    return sum(closes[-period:]) / period


class SyncExecutor(BaseExecutor):
    """
    Однопоточный режим: из очереди получаем MarketData, для каждой стратегии
    добавляем fast_ma/slow_ma из кэша свечей и вызываем on_tick -> apply_signal.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._queue: "queue.Queue[MarketData]" = queue.Queue()
        self._klines: dict[Tuple[str, str], List[dict]] = {}  # (symbol, interval) -> свечи

    def run(self) -> None:
        """Основной цикл: get из очереди -> обогащение MA -> стратегии -> OrderManager."""
        log.info("SyncExecutor started")
        while not self._stopped:
            try:
                market_data = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            for strategy in self.strategies:
                if market_data.symbol != strategy.symbol:
                    continue
                md = self._enrich_with_ma(market_data, strategy)
                signal = strategy.on_tick(md)
                if signal:
                    self.order_manager.apply_signal(signal, md)
        log.info("SyncExecutor stopped")

    def _enrich_with_ma(self, market_data: MarketData, strategy: BaseStrategy) -> MarketData:
        """Добавить в extra fast_ma и slow_ma из кэша свечей по (symbol, timeframe)."""
        key = (market_data.symbol, strategy.timeframe)
        klines = self._klines.get(key, [])
        closes = []
        for k in klines:
            if isinstance(k, dict):
                c = k.get("c") or k.get("close")
                if c is not None:
                    closes.append(float(c))
            else:
                closes.append(float(k))
        p = strategy.get_params()
        fast_period = p.get("fast_period", 10)
        slow_period = p.get("slow_period", 20)
        fast_ma = _compute_ma(closes, fast_period)
        slow_ma = _compute_ma(closes, slow_period)
        extra = dict(market_data.extra)
        if fast_ma is not None:
            extra["fast_ma"] = fast_ma
        if slow_ma is not None:
            extra["slow_ma"] = slow_ma
        return MarketData(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            price=market_data.price,
            timestamp=market_data.timestamp,
            extra=extra,
        )

    def stop(self) -> None:
        super().stop()

    def feed(self, market_data: MarketData) -> None:
        """Вызывается потоком WebSocket при новом тикере — кладём в очередь."""
        self._queue.put(market_data)

    def feed_klines(self, symbol: str, interval: str, kline_list: List[Any]) -> None:
        """Обновить кэш свечей для расчёта MA. interval — строка, например '15' (минуты)."""
        if not kline_list:
            return
        key = (symbol, str(interval))
        existing = self._klines.get(key, [])
        for k in kline_list:
            if isinstance(k, dict):
                existing.append(k)
            else:
                existing.append(k)
        self._klines[key] = existing[-200:]  # keep last 200 candles
