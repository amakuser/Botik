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
        self.last_summary: dict[str, int] = {}

    def get_last_summary(self) -> dict[str, int]:
        return dict(self.last_summary)

    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        if state.paused:
            self.last_summary = {"paused": 1}
            return []

        symbols = state.get_active_symbols() or self.config.symbols
        intents: list[OrderIntent] = []
        summary: dict[str, int] = {
            "symbols_total": len(symbols),
            "universe_total": len(self.config.symbols),
            "no_orderbook": 0,
            "spread_reject": 0,
            "cooldown_reject": 0,
            "edge_or_liquidity_reject": 0,
            "invalid_quote_reject": 0,
            "maker_guard_reject": 0,
            "symbols_quoted": 0,
        }
        now = time.monotonic()
        replace_interval_sec = self.config.strategy.replace_interval_ms / 1000.0
        min_spread_ticks = self.config.strategy.min_spread_ticks
        default_tick_size = self.config.strategy.default_tick_size
        profiles_by_id = {
            p.profile_id.strip(): p
            for p in self.config.strategy.action_profiles
            if p.profile_id and p.profile_id.strip()
        }
        default_profile_id = next(iter(profiles_by_id.keys()), None)

        for symbol in symbols:
            ob = state.get_orderbook(symbol)
            if ob is None:
                summary["no_orderbook"] += 1
                continue

            active_profile_id = state.get_active_profile_id(symbol) or default_profile_id
            active_profile = profiles_by_id.get(active_profile_id or "")
            entry_tick_offset = (
                active_profile.entry_tick_offset
                if active_profile is not None
                else self.config.strategy.entry_tick_offset
            )
            order_qty = (
                active_profile.order_qty_base
                if active_profile is not None
                else self.config.strategy.order_qty_base
            )
            target_profit = (
                active_profile.target_profit
                if active_profile is not None
                else self.config.strategy.target_profit
            )
            safety_buffer = (
                active_profile.safety_buffer
                if active_profile is not None
                else self.config.strategy.safety_buffer
            )
            min_top_book_qty = (
                active_profile.min_top_book_qty
                if active_profile is not None
                else self.config.strategy.min_top_book_qty
            )
            # Entries are always maker-only.
            maker_only = True

            fee_rate = self.config.fees.maker_rate
            # Keep scanner fee assumptions aligned with pair admission profile.
            if self.config.strategy.strict_pair_filter:
                bootstrap_buy_fee = max(self.config.strategy.bootstrap_fee_entry_bps, 0.0) / 10000.0
                bootstrap_sell_fee = max(self.config.strategy.bootstrap_fee_exit_bps, 0.0) / 10000.0
                # Conservative mode: do not underestimate fees vs configured trading fee.
                buy_fee = max(max(fee_rate, 0.0), bootstrap_buy_fee) if bootstrap_buy_fee > 0 else max(fee_rate, 0.0)
                sell_fee = max(max(fee_rate, 0.0), bootstrap_sell_fee) if bootstrap_sell_fee > 0 else max(fee_rate, 0.0)
            else:
                buy_fee = fee_rate
                sell_fee = fee_rate

            tick_size = state.get_tick_size(symbol) or default_tick_size
            if ob.spread_ticks < min_spread_ticks:
                summary["spread_reject"] += 1
                continue
            spread_bps_now = ((ob.best_ask - ob.best_bid) / ob.mid) * 10000.0 if ob.mid > 0 and ob.best_ask >= ob.best_bid else 0.0
            if spread_bps_now < max(float(self.config.strategy.min_spread_bps), 0.0):
                summary["spread_reject"] += 1
                continue

            last = self._last_replace_time.get(symbol, 0.0)
            if now - last < replace_interval_sec:
                summary["cooldown_reject"] += 1
                continue

            scan = scan_spread(
                best_bid=ob.best_bid,
                best_ask=ob.best_ask,
                best_bid_size=ob.best_bid_size,
                best_ask_size=ob.best_ask_size,
                tick_size=tick_size,
                entry_tick_offset=entry_tick_offset,
                buy_fee=buy_fee,
                sell_fee=sell_fee,
                target_profit=target_profit,
                safety_buffer=safety_buffer,
                min_top_book_qty=min_top_book_qty,
            )
            if not scan.tradable:
                logger.debug(
                    "skip %s: %s (edge=%.6f required=%.6f)",
                    symbol,
                    scan.reason,
                    scan.net_edge,
                    scan.required_edge,
                )
                summary["edge_or_liquidity_reject"] += 1
                continue

            bid_price = round(scan.entry_price / tick_size) * tick_size
            ask_price = round(scan.exit_price / tick_size) * tick_size
            if bid_price <= 0 or ask_price <= 0 or ask_price <= bid_price:
                summary["invalid_quote_reject"] += 1
                continue

            if maker_only and (bid_price >= ob.best_ask or ask_price <= ob.best_bid):
                logger.debug("skip %s: maker_only guard (bid=%.8f ask=%.8f)", symbol, bid_price, ask_price)
                summary["maker_guard_reject"] += 1
                continue

            self._last_replace_time[symbol] = now
            bid_link = f"mm-{symbol}-bid-{uuid.uuid4().hex[:12]}"
            ask_link = f"mm-{symbol}-ask-{uuid.uuid4().hex[:12]}"
            intents.append(
                OrderIntent(
                    symbol=symbol,
                    side="Buy",
                    price=bid_price,
                    qty=order_qty,
                    order_link_id=bid_link,
                    profile_id=active_profile_id,
                    model_version="rules-v1",
                    action_entry_tick_offset=entry_tick_offset,
                    action_order_qty_base=order_qty,
                    action_target_profit=target_profit,
                    action_safety_buffer=safety_buffer,
                    action_min_top_book_qty=min_top_book_qty,
                    action_stop_loss_pct=active_profile.stop_loss_pct if active_profile is not None else None,
                    action_take_profit_pct=active_profile.take_profit_pct if active_profile is not None else None,
                    action_hold_timeout_sec=active_profile.hold_timeout_sec if active_profile is not None else None,
                    action_maker_only=maker_only,
                )
            )
            intents.append(
                OrderIntent(
                    symbol=symbol,
                    side="Sell",
                    price=ask_price,
                    qty=order_qty,
                    order_link_id=ask_link,
                    profile_id=active_profile_id,
                    model_version="rules-v1",
                    action_entry_tick_offset=entry_tick_offset,
                    action_order_qty_base=order_qty,
                    action_target_profit=target_profit,
                    action_safety_buffer=safety_buffer,
                    action_min_top_book_qty=min_top_book_qty,
                    action_stop_loss_pct=active_profile.stop_loss_pct if active_profile is not None else None,
                    action_take_profit_pct=active_profile.take_profit_pct if active_profile is not None else None,
                    action_hold_timeout_sec=active_profile.hold_timeout_sec if active_profile is not None else None,
                    action_maker_only=maker_only,
                )
            )
            summary["symbols_quoted"] += 1

        summary["intents"] = len(intents)
        self.last_summary = summary
        return intents
