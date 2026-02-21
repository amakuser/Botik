"""
In-memory состояние: стаканы по символам (best bid/ask, mid, spread_ticks, imbalance),
флаг paused (торговля выключена до /resume).
Сырой стакан на диск не пишем — только агрегаты через storage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrderBookAggregate:
    """Агрегат стакана для одного символа (для стратегии и записи в metrics)."""
    symbol: str
    best_bid: float
    best_ask: float
    mid: float
    spread_ticks: int
    imbalance_top_n: float  # (bid_vol - ask_vol) / (bid_vol + ask_vol) для top N
    ts_utc: str = ""


@dataclass
class TradingState:
    """
    Глобальное состояние: стаканы по символам, флаг paused, запрос panic.
    Обновляется из ws_public и из Telegram; читается стратегией и main loop.
    """
    orderbooks: dict[str, OrderBookAggregate] = field(default_factory=dict)
    paused: bool = True  # start_paused: пока True — стратегия не шлёт intents
    panic_requested: bool = False  # /panic: main loop отменяет все ордера (и опционально market close)

    def set_orderbook(self, symbol: str, agg: OrderBookAggregate) -> None:
        self.orderbooks[symbol] = agg

    def get_orderbook(self, symbol: str) -> OrderBookAggregate | None:
        return self.orderbooks.get(symbol)

    def set_paused(self, value: bool) -> None:
        self.paused = value

    def set_panic_requested(self, value: bool) -> None:
        self.panic_requested = value


def compute_imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], top_n: int = 10) -> float:
    """
    Импбаланс топ-N уровней: (sum_bid_vol - sum_ask_vol) / (sum_bid_vol + sum_ask_vol).
    Возвращает значение в [-1, 1]; 0 — сбалансировано.
    """
    b_vol = sum(sz for _, sz in bids[:top_n])
    a_vol = sum(sz for _, sz in asks[:top_n])
    total = b_vol + a_vol
    if total <= 0:
        return 0.0
    return (b_vol - a_vol) / total


# --- Как проверить: создать TradingState(), set_orderbook с OrderBookAggregate, get_orderbook.
# --- Частые ошибки: не обновлять ts_utc при обновлении стакана; читать стакан из другого потока без блокировки (для asyncio один поток — ок).
# --- Что улучшить позже: threading.Lock при многопоточности; last_mid по символу для конвертации fee.
