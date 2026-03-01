"""
In-memory runtime state for market aggregates and control flags.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrderBookAggregate:
    symbol: str
    best_bid: float
    best_ask: float
    mid: float
    spread_ticks: int
    imbalance_top_n: float
    best_bid_size: float = 0.0
    best_ask_size: float = 0.0
    ts_utc: str = ""


@dataclass
class TradingState:
    orderbooks: dict[str, OrderBookAggregate] = field(default_factory=dict)
    paused: bool = True
    panic_requested: bool = False

    def set_orderbook(self, symbol: str, agg: OrderBookAggregate) -> None:
        self.orderbooks[symbol] = agg

    def get_orderbook(self, symbol: str) -> OrderBookAggregate | None:
        return self.orderbooks.get(symbol)

    def set_paused(self, value: bool) -> None:
        self.paused = value

    def set_panic_requested(self, value: bool) -> None:
        self.panic_requested = value


def compute_imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], top_n: int = 10) -> float:
    b_vol = sum(sz for _, sz in bids[:top_n])
    a_vol = sum(sz for _, sz in asks[:top_n])
    total = b_vol + a_vol
    if total <= 0:
        return 0.0
    return (b_vol - a_vol) / total
