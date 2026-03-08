"""
In-memory runtime state for market aggregates and control flags.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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
    ts_ms: int = 0
    ts_utc: str = ""


@dataclass(frozen=True)
class PublicTradeEvent:
    symbol: str
    trade_id: str
    seq: int
    ts_ms: int
    taker_side: str
    price: float
    qty: float


@dataclass
class TradingState:
    orderbooks: dict[str, OrderBookAggregate] = field(default_factory=dict)
    orderbook_levels: dict[str, tuple[list[tuple[float, float]], list[tuple[float, float]]]] = field(default_factory=dict)
    symbol_tick_size: dict[str, float] = field(default_factory=dict)
    book_snapshot_ready: dict[str, bool] = field(default_factory=dict)
    last_book_update_ms: dict[str, int] = field(default_factory=dict)
    last_trade_update_ms: dict[str, int] = field(default_factory=dict)
    spread_bps_history: dict[str, deque[tuple[int, float]]] = field(default_factory=dict)
    mid_history: dict[str, deque[tuple[int, float]]] = field(default_factory=dict)
    public_trades: dict[str, deque[PublicTradeEvent]] = field(default_factory=dict)
    pair_filter_snapshot: dict[str, dict[str, Any]] = field(default_factory=dict)
    pair_gate_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    paused: bool = True
    panic_requested: bool = False
    active_symbols: list[str] = field(default_factory=list)
    active_profiles: dict[str, str] = field(default_factory=dict)
    active_policy_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    scanner_snapshot: dict[str, Any] = field(default_factory=dict)
    update_in_progress: bool = False
    restart_requested: bool = False
    current_version: str = ""
    update_message: str = ""

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _prune_time_series(
        self,
        store: dict[str, deque[tuple[int, float]]],
        symbol: str,
        now_ms: int,
        max_age_ms: int = 15 * 60 * 1000,
    ) -> None:
        series = store.setdefault(symbol, deque())
        while series and now_ms - series[0][0] > max_age_ms:
            series.popleft()

    def set_orderbook(
        self,
        symbol: str,
        agg: OrderBookAggregate,
        bids: list[tuple[float, float]] | None = None,
        asks: list[tuple[float, float]] | None = None,
        is_snapshot: bool = False,
        tick_size: float | None = None,
    ) -> None:
        self.orderbooks[symbol] = agg
        if tick_size is not None and tick_size > 0:
            self.symbol_tick_size[symbol] = float(tick_size)
        ts_ms = agg.ts_ms or self._now_ms()
        self.last_book_update_ms[symbol] = ts_ms
        if is_snapshot:
            self.book_snapshot_ready[symbol] = True
        elif symbol not in self.book_snapshot_ready:
            self.book_snapshot_ready[symbol] = False
        if bids is not None and asks is not None:
            self.orderbook_levels[symbol] = (bids, asks)

        if agg.mid > 0 and agg.best_ask > agg.best_bid > 0:
            spread_abs = agg.best_ask - agg.best_bid
            spread_bps = (spread_abs / agg.mid) * 10000.0
            spread_series = self.spread_bps_history.setdefault(symbol, deque())
            spread_series.append((ts_ms, spread_bps))
            self._prune_time_series(self.spread_bps_history, symbol, ts_ms)

        if agg.mid > 0:
            mid_series = self.mid_history.setdefault(symbol, deque())
            mid_series.append((ts_ms, agg.mid))
            self._prune_time_series(self.mid_history, symbol, ts_ms)

    def get_orderbook(self, symbol: str) -> OrderBookAggregate | None:
        return self.orderbooks.get(symbol)

    def get_orderbook_levels(self, symbol: str) -> tuple[list[tuple[float, float]], list[tuple[float, float]]] | None:
        return self.orderbook_levels.get(symbol)

    def get_tick_size(self, symbol: str) -> float | None:
        value = self.symbol_tick_size.get(symbol)
        if value is None or value <= 0:
            return None
        return float(value)

    def is_book_snapshot_ready(self, symbol: str) -> bool:
        return bool(self.book_snapshot_ready.get(symbol, False))

    def get_last_book_update_ms(self, symbol: str) -> int | None:
        return self.last_book_update_ms.get(symbol)

    def record_public_trade(self, event: PublicTradeEvent) -> None:
        symbol = event.symbol
        trades = self.public_trades.setdefault(symbol, deque())
        trades.append(event)
        self.last_trade_update_ms[symbol] = event.ts_ms
        while len(trades) > 100000:
            trades.popleft()
        # Keep ~15 minutes of trade tape in memory.
        cutoff = event.ts_ms - (15 * 60 * 1000)
        while trades and trades[0].ts_ms < cutoff:
            trades.popleft()

    def get_public_trades(self, symbol: str) -> list[PublicTradeEvent]:
        return list(self.public_trades.get(symbol, []))

    def get_last_trade_update_ms(self, symbol: str) -> int | None:
        return self.last_trade_update_ms.get(symbol)

    def get_spread_bps_series(self, symbol: str) -> list[tuple[int, float]]:
        return list(self.spread_bps_history.get(symbol, []))

    def get_mid_series(self, symbol: str) -> list[tuple[int, float]]:
        return list(self.mid_history.get(symbol, []))

    def set_pair_filter_snapshot(self, symbol: str, snapshot: dict[str, Any]) -> None:
        self.pair_filter_snapshot[symbol] = dict(snapshot)

    def get_pair_filter_snapshot(self, symbol: str) -> dict[str, Any] | None:
        value = self.pair_filter_snapshot.get(symbol)
        return dict(value) if value is not None else None

    def get_all_pair_filter_snapshots(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self.pair_filter_snapshot.items()}

    def set_pair_gate_state(self, symbol: str, state: dict[str, Any]) -> None:
        self.pair_gate_state[symbol] = dict(state)

    def get_pair_gate_state(self, symbol: str) -> dict[str, Any]:
        return dict(self.pair_gate_state.get(symbol, {}))

    def set_paused(self, value: bool) -> None:
        self.paused = value

    def set_panic_requested(self, value: bool) -> None:
        self.panic_requested = value

    def set_active_symbols(self, symbols: list[str]) -> None:
        self.active_symbols = list(symbols)

    def get_active_symbols(self) -> list[str]:
        return list(self.active_symbols)

    def set_active_profiles(self, profiles: dict[str, str]) -> None:
        self.active_profiles = {str(symbol): str(profile_id) for symbol, profile_id in profiles.items() if profile_id}

    def get_active_profiles(self) -> dict[str, str]:
        return dict(self.active_profiles)

    def get_active_profile_id(self, symbol: str) -> str | None:
        value = self.active_profiles.get(symbol)
        if not value:
            return None
        return str(value)

    def set_active_policy_meta(self, meta: dict[str, dict[str, Any]]) -> None:
        self.active_policy_meta = {str(symbol): dict(values) for symbol, values in meta.items()}

    def get_active_policy_meta(self, symbol: str) -> dict[str, Any]:
        return dict(self.active_policy_meta.get(symbol, {}))

    def get_all_active_policy_meta(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self.active_policy_meta.items()}

    def set_scanner_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.scanner_snapshot = dict(snapshot)

    def get_scanner_snapshot(self) -> dict[str, Any]:
        return dict(self.scanner_snapshot)

    def set_update_in_progress(self, value: bool, message: str | None = None) -> None:
        self.update_in_progress = bool(value)
        if message is not None:
            self.update_message = str(message)

    def set_restart_requested(self, value: bool) -> None:
        self.restart_requested = bool(value)

    def set_current_version(self, version: str) -> None:
        self.current_version = str(version or "").strip()

    def get_current_version(self) -> str:
        return str(self.current_version or "")

    def get_update_message(self) -> str:
        return str(self.update_message or "")


def compute_imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], top_n: int = 10) -> float:
    b_vol = sum(sz for _, sz in bids[:top_n])
    a_vol = sum(sz for _, sz in asks[:top_n])
    total = b_vol + a_vol
    if total <= 0:
        return 0.0
    return (b_vol - a_vol) / total
