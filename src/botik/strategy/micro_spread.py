"""
Micro spread strategy with spread scanner and maker-style quotes.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from src.botik.risk.manager import OrderIntent
from src.botik.strategy.base import BaseStrategy
from src.botik.strategy.spread_scanner import scan_spread

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState

logger = logging.getLogger(__name__)


class MicroSpreadStrategy(BaseStrategy):
    def __init__(self, config: "AppConfig") -> None:
        self.config = config
        self._last_replace_time: dict[str, float] = {}

    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        if state.paused:
            return []

        intents: list[OrderIntent] = []
        now = time.monotonic()
        replace_interval_sec = self.config.strategy.replace_interval_ms / 1000.0
        min_spread_ticks = self.config.strategy.min_spread_ticks
        tick_size = self.config.strategy.default_tick_size
        maker_only = self.config.strategy.maker_only
        order_qty = self.config.strategy.order_qty_base

        fee_rate = self.config.fees.maker_rate if maker_only else self.config.fees.taker_rate

        for symbol in self.config.symbols:
            ob = state.get_orderbook(symbol)
            if ob is None:
                continue
            if ob.spread_ticks < min_spread_ticks:
                continue

            last = self._last_replace_time.get(symbol, 0.0)
            if now - last < replace_interval_sec:
                continue

            scan = scan_spread(
                best_bid=ob.best_bid,
                best_ask=ob.best_ask,
                best_bid_size=ob.best_bid_size,
                best_ask_size=ob.best_ask_size,
                tick_size=tick_size,
                entry_tick_offset=self.config.strategy.entry_tick_offset,
                buy_fee=fee_rate,
                sell_fee=fee_rate,
                target_profit=self.config.strategy.target_profit,
                safety_buffer=self.config.strategy.safety_buffer,
                min_top_book_qty=self.config.strategy.min_top_book_qty,
            )
            if not scan.tradable:
                logger.debug(
                    "skip %s: %s (edge=%.6f required=%.6f)",
                    symbol,
                    scan.reason,
                    scan.net_edge,
                    scan.required_edge,
                )
                continue

            bid_price = round(scan.entry_price / tick_size) * tick_size
            ask_price = round(scan.exit_price / tick_size) * tick_size
            if bid_price <= 0 or ask_price <= 0 or ask_price <= bid_price:
                continue

            if maker_only and (bid_price >= ob.best_ask or ask_price <= ob.best_bid):
                logger.debug("skip %s: maker_only guard (bid=%.8f ask=%.8f)", symbol, bid_price, ask_price)
                continue

            self._last_replace_time[symbol] = now
            bid_link = f"mm-{symbol}-bid-{uuid.uuid4().hex[:12]}"
            ask_link = f"mm-{symbol}-ask-{uuid.uuid4().hex[:12]}"
            intents.append(OrderIntent(symbol=symbol, side="Buy", price=bid_price, qty=order_qty, order_link_id=bid_link))
            intents.append(OrderIntent(symbol=symbol, side="Sell", price=ask_price, qty=order_qty, order_link_id=ask_link))

        return intents
