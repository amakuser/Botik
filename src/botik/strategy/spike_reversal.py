"""
Spike reversal strategy for fast directional moves.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from src.botik.risk.manager import OrderIntent
from src.botik.strategy.base import BaseStrategy

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class SpikeReversalStrategy(BaseStrategy):
    def __init__(self, config: "AppConfig") -> None:
        self.config = config
        self._last_trigger_mono: dict[str, float] = {}
        self.last_summary: dict[str, int] = {}

    def get_last_summary(self) -> dict[str, int]:
        return dict(self.last_summary)

    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        if state.paused:
            self.last_summary = {"paused": 1}
            return []

        active_symbols = state.get_active_symbols()
        if self.config.strategy.scanner_enabled:
            scanner_ready = bool(state.get_scanner_snapshot())
            symbols = active_symbols if scanner_ready else (active_symbols or self.config.symbols)
        else:
            symbols = active_symbols or self.config.symbols

        summaries: list[tuple[str, int, float]] = []
        for symbol in symbols:
            snap = state.get_pair_filter_snapshot(symbol) or {}
            spike_dir = _safe_int(snap.get("spike_direction"), 0)
            spike_strength = _safe_float(snap.get("spike_strength_bps"), 0.0)
            summaries.append((symbol, spike_dir, spike_strength))
        summaries.sort(key=lambda x: abs(x[2]), reverse=True)

        max_symbols = max(int(self.config.strategy.spike_reversal_max_symbols), 1)
        ordered_symbols = [s for s, _d, _m in summaries[:max_symbols]]

        profiles_by_id = {
            p.profile_id.strip(): p
            for p in self.config.strategy.action_profiles
            if p.profile_id and p.profile_id.strip()
        }
        default_profile_id = next(iter(profiles_by_id.keys()), None)

        min_strength = max(
            float(self.config.strategy.spike_reversal_min_strength_bps),
            float(self.config.strategy.spike_threshold_bps),
            0.0,
        )
        reverse_enabled = bool(self.config.strategy.spike_reversal_reverse)
        maker_only = not bool(self.config.strategy.spike_reversal_taker)
        qty_scale = max(float(self.config.strategy.spike_reversal_qty_scale), 0.01)
        entry_offset = max(int(self.config.strategy.spike_reversal_entry_offset_ticks), 0)
        cooldown_sec = max(float(self.config.strategy.spike_reversal_cooldown_sec), 0.1)
        default_tick_size = max(float(self.config.strategy.default_tick_size), 1e-12)
        # Notional-based sizing: use order_notional_quote (USDT) to compute qty
        # so that each order has consistent dollar size regardless of coin price.
        order_notional_quote = max(float(self.config.strategy.order_notional_quote), 1.0)

        intents: list[OrderIntent] = []
        summary: dict[str, int] = {
            "symbols_total": len(symbols),
            "symbols_selected": len(ordered_symbols),
            "no_orderbook": 0,
            "below_threshold": 0,
            "cooldown_reject": 0,
            "invalid_quote_reject": 0,
            "maker_guard_reject": 0,
            "symbols_triggered": 0,
            "intents": 0,
        }

        now = time.monotonic()
        for symbol in ordered_symbols:
            ob = state.get_orderbook(symbol)
            if ob is None:
                summary["no_orderbook"] += 1
                continue
            if ob.best_bid <= 0 or ob.best_ask <= 0 or ob.best_ask <= ob.best_bid:
                summary["invalid_quote_reject"] += 1
                continue

            pair_snapshot = state.get_pair_filter_snapshot(symbol) or {}
            spike_direction = _safe_int(pair_snapshot.get("spike_direction"), 0)
            spike_strength_bps = _safe_float(pair_snapshot.get("spike_strength_bps"), 0.0)
            if abs(spike_direction) != 1 or spike_strength_bps < min_strength:
                summary["below_threshold"] += 1
                continue

            last = self._last_trigger_mono.get(symbol, 0.0)
            if now - last < cooldown_sec:
                summary["cooldown_reject"] += 1
                continue

            active_profile_id = state.get_active_profile_id(symbol) or default_profile_id
            active_profile = profiles_by_id.get(active_profile_id or "")
            if active_profile is not None:
                hold_timeout_sec = active_profile.hold_timeout_sec
                stop_loss_pct = active_profile.stop_loss_pct
                take_profit_pct = active_profile.take_profit_pct
            else:
                hold_timeout_sec = self.config.strategy.position_hold_timeout_sec
                stop_loss_pct = self.config.strategy.stop_loss_pct
                take_profit_pct = self.config.strategy.take_profit_pct

            if reverse_enabled:
                side = "Sell" if spike_direction > 0 else "Buy"
            else:
                side = "Buy" if spike_direction > 0 else "Sell"

            tick_size = state.get_tick_size(symbol) or default_tick_size
            tick_size = max(float(tick_size), 1e-12)
            if maker_only:
                if side == "Buy":
                    target_price = ob.best_bid + (entry_offset * tick_size)
                    if target_price >= ob.best_ask:
                        target_price = ob.best_bid
                else:
                    target_price = ob.best_ask - (entry_offset * tick_size)
                    if target_price <= ob.best_bid:
                        target_price = ob.best_ask
            else:
                if side == "Buy":
                    target_price = ob.best_ask + (entry_offset * tick_size)
                else:
                    target_price = ob.best_bid - (entry_offset * tick_size)

            price = round(float(target_price) / tick_size) * tick_size
            if price <= 0:
                summary["invalid_quote_reject"] += 1
                continue
            if maker_only:
                if side == "Buy" and price >= ob.best_ask:
                    summary["maker_guard_reject"] += 1
                    continue
                if side == "Sell" and price <= ob.best_bid:
                    summary["maker_guard_reject"] += 1
                    continue

            # --- Notional-based qty: order_notional_quote * qty_scale / price ---
            # This ensures consistent USDT sizing across all symbols.
            # E.g. order_notional_quote=50, qty_scale=0.25 → ~$12.50 per order.
            target_notional = order_notional_quote * qty_scale
            qty = max(target_notional / price, 1e-12)
            log.debug(
                "SpikeReversal intent: symbol=%s side=%s price=%.8f qty=%.8f notional=%.4f",
                symbol, side, price, qty, price * qty,
            )

            order_link_id = f"spkrev-{symbol}-{uuid.uuid4().hex[:12]}"
            intents.append(
                OrderIntent(
                    symbol=symbol,
                    side=side,
                    price=price,
                    qty=qty,
                    order_link_id=order_link_id,
                    profile_id=active_profile_id,
                    model_version="spike-reversal-v1",
                    action_entry_tick_offset=entry_offset,
                    action_order_qty_base=qty,
                    action_target_profit=float(self.config.strategy.target_profit),
                    action_safety_buffer=float(self.config.strategy.safety_buffer),
                    action_min_top_book_qty=float(self.config.strategy.min_top_book_qty),
                    action_stop_loss_pct=stop_loss_pct,
                    action_take_profit_pct=take_profit_pct,
                    action_hold_timeout_sec=hold_timeout_sec,
                    action_maker_only=maker_only,
                )
            )
            self._last_trigger_mono[symbol] = now
            summary["symbols_triggered"] += 1

        summary["intents"] = len(intents)
        self.last_summary = summary
        return intents
