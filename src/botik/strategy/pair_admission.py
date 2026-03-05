"""
Pair admission filter for spread strategy (PASS/WATCH/REJECT).
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState


@dataclass(frozen=True)
class PairAdmissionDecision:
    symbol: str
    status: str
    reason: str
    stale_data: bool
    data_age_ms: int
    metrics: dict[str, float | int | bool | str]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    rank = max(0.0, min(100.0, p)) / 100.0 * (len(vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


def _simulate_vwap_buy(asks: list[tuple[float, float]], order_notional_quote: float) -> float | None:
    remaining_quote = order_notional_quote
    total_base = 0.0
    total_quote = 0.0
    for price, qty in asks:
        if price <= 0 or qty <= 0 or remaining_quote <= 0:
            continue
        level_quote = price * qty
        take_quote = min(remaining_quote, level_quote)
        take_base = take_quote / price
        total_quote += take_quote
        total_base += take_base
        remaining_quote -= take_quote
        if remaining_quote <= 0:
            break
    if remaining_quote > 0 or total_base <= 0:
        return None
    return total_quote / total_base


def _simulate_vwap_sell(bids: list[tuple[float, float]], order_notional_quote: float) -> float | None:
    remaining_quote_target = order_notional_quote
    total_base = 0.0
    total_quote = 0.0
    for price, qty in bids:
        if price <= 0 or qty <= 0 or remaining_quote_target <= 0:
            continue
        level_quote = price * qty
        take_quote = min(remaining_quote_target, level_quote)
        take_base = take_quote / price
        total_quote += take_quote
        total_base += take_base
        remaining_quote_target -= take_quote
        if remaining_quote_target <= 0:
            break
    if remaining_quote_target > 0 or total_base <= 0:
        return None
    return total_quote / total_base


def _depth_near_mid_quote(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    mid: float,
    depth_band_bps: float,
) -> tuple[float, float]:
    if mid <= 0:
        return 0.0, 0.0
    band = max(depth_band_bps, 0.0) / 10000.0
    low = mid * (1.0 - band)
    high = mid * (1.0 + band)
    depth_bid_quote = sum(price * qty for price, qty in bids if low <= price <= mid)
    depth_ask_quote = sum(price * qty for price, qty in asks if mid <= price <= high)
    return depth_bid_quote, depth_ask_quote


def _bps_changes_from_mid_series(mid_series: list[tuple[int, float]]) -> list[float]:
    if not mid_series:
        return []
    second_mid: dict[int, float] = {}
    for ts_ms, mid in mid_series:
        if mid > 0:
            second_mid[int(ts_ms // 1000)] = mid
    points = sorted(second_mid.items(), key=lambda x: x[0])
    changes: list[float] = []
    for idx in range(1, len(points)):
        prev_mid = points[idx - 1][1]
        cur_mid = points[idx][1]
        if prev_mid <= 0:
            continue
        changes.append(((cur_mid - prev_mid) / prev_mid) * 10000.0)
    return changes


def evaluate_pair_admission(
    symbol: str,
    state: "TradingState",
    config: "AppConfig",
    now_ms: int | None = None,
) -> PairAdmissionDecision:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    s_cfg = config.strategy

    ob = state.get_orderbook(symbol)
    levels = state.get_orderbook_levels(symbol)
    snapshot_ready = state.is_book_snapshot_ready(symbol)
    book_ts = state.get_last_book_update_ms(symbol)
    trade_ts = state.get_last_trade_update_ms(symbol)

    book_age_ms = (now - book_ts) if book_ts is not None else 10**9
    trade_age_ms = (now - trade_ts) if trade_ts is not None else 10**9
    data_age_ms = max(book_age_ms, trade_age_ms)
    stale_data = (
        (not snapshot_ready)
        or (book_age_ms > s_cfg.max_book_silence_ms)
        or (trade_age_ms > s_cfg.max_trade_silence_ms)
        or ob is None
        or levels is None
    )

    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    if levels is not None:
        bids, asks = levels

    spread_series = [
        v
        for ts, v in state.get_spread_bps_series(symbol)
        if now - ts <= max(int(s_cfg.spread_window_sec), 1) * 1000
    ]
    median_spread_bps = statistics.median(spread_series) if spread_series else 0.0
    p25_spread_bps = _percentile(spread_series, 25.0) if spread_series else 0.0
    p75_spread_bps = _percentile(spread_series, 75.0) if spread_series else 0.0

    trades = [t for t in state.get_public_trades(symbol) if now - t.ts_ms <= max(int(s_cfg.trade_window_sec), 1) * 1000]
    trades_per_min = len(trades) * 60.0 / max(float(s_cfg.trade_window_sec), 1.0)
    trade_gaps_ms: list[float] = []
    for idx in range(1, len(trades)):
        trade_gaps_ms.append(float(trades[idx].ts_ms - trades[idx - 1].ts_ms))
    median_trade_gap_ms = statistics.median(trade_gaps_ms) if trade_gaps_ms else float("inf")
    p95_trade_gap_ms = _percentile(trade_gaps_ms, 95.0) if trade_gaps_ms else float("inf")
    max_trade_gap_ms_window = max(trade_gaps_ms) if trade_gaps_ms else float("inf")

    depth_bid_quote = 0.0
    depth_ask_quote = 0.0
    best_bid = ob.best_bid if ob is not None else 0.0
    best_ask = ob.best_ask if ob is not None else 0.0
    mid = ob.mid if ob is not None else 0.0
    if bids and asks and mid > 0:
        depth_bid_quote, depth_ask_quote = _depth_near_mid_quote(
            bids=bids,
            asks=asks,
            mid=mid,
            depth_band_bps=s_cfg.depth_band_bps,
        )

    vwap_buy = _simulate_vwap_buy(asks, s_cfg.order_notional_quote) if asks else None
    vwap_sell = _simulate_vwap_sell(bids, s_cfg.order_notional_quote) if bids else None
    fallback_slippage_one_side_bps = max(s_cfg.max_total_slippage_bps, 0.0) / 2.0
    slippage_buy_bps = (
        ((vwap_buy - best_ask) / best_ask) * 10000.0
        if (vwap_buy is not None and best_ask > 0)
        else fallback_slippage_one_side_bps
    )
    slippage_sell_bps = (
        ((best_bid - vwap_sell) / best_bid) * 10000.0
        if (vwap_sell is not None and best_bid > 0)
        else fallback_slippage_one_side_bps
    )
    total_slippage_bps = max(slippage_buy_bps, 0.0) + max(slippage_sell_bps, 0.0)

    configured_fee_bps = (
        max(config.fees.maker_rate, 0.0) * 10000.0
        if s_cfg.maker_only_entry
        else max(config.fees.taker_rate, 0.0) * 10000.0
    )
    fee_entry_bps = max(s_cfg.bootstrap_fee_entry_bps, configured_fee_bps)
    fee_exit_bps = max(s_cfg.bootstrap_fee_exit_bps, configured_fee_bps)
    min_required_spread_bps = (
        fee_entry_bps
        + fee_exit_bps
        + max(slippage_buy_bps, 0.0)
        + max(slippage_sell_bps, 0.0)
        + s_cfg.safety_buffer_bps
        + s_cfg.target_edge_bps
    )

    mid_window = [p for p in state.get_mid_series(symbol) if now - p[0] <= max(int(s_cfg.vol_window_sec), 1) * 1000]
    move_1s_bps = _bps_changes_from_mid_series(mid_window)
    vol_1s_bps = statistics.pstdev(move_1s_bps) if len(move_1s_bps) >= 2 else 0.0
    p95_abs_move_1s_bps = _percentile([abs(v) for v in move_1s_bps], 95.0) if move_1s_bps else 0.0

    depth_floor = s_cfg.order_notional_quote * s_cfg.min_depth_multiplier
    cond_trades = trades_per_min >= s_cfg.min_trades_per_min
    cond_gap_p95 = p95_trade_gap_ms <= float(s_cfg.max_p95_trade_gap_ms)
    cond_gap_max = max_trade_gap_ms_window <= float(s_cfg.max_max_gap_ms)
    cond_depth = min(depth_bid_quote, depth_ask_quote) >= depth_floor
    cond_slippage = total_slippage_bps <= s_cfg.max_total_slippage_bps
    cond_spread = median_spread_bps >= min_required_spread_bps
    cond_vol = vol_1s_bps <= (median_spread_bps * s_cfg.max_vol_to_spread_ratio if median_spread_bps > 0 else 0.0)

    failed: list[str] = []
    if not cond_trades:
        failed.append("trades_per_min")
    if not cond_gap_p95:
        failed.append("p95_trade_gap")
    if not cond_gap_max:
        failed.append("max_trade_gap")
    if not cond_depth:
        failed.append("depth")
    if not cond_slippage:
        failed.append("slippage")
    if not cond_spread:
        failed.append("spread")
    if not cond_vol:
        failed.append("vol")

    critical = (
        stale_data
        or (not cond_depth and min(depth_bid_quote, depth_ask_quote) < depth_floor * 0.5)
        or (not cond_gap_max and max_trade_gap_ms_window > s_cfg.max_max_gap_ms * 1.5)
        or (not cond_slippage and total_slippage_bps > s_cfg.max_total_slippage_bps * 1.5)
    )

    gate = state.get_pair_gate_state(symbol)
    cooldown_until_ms = int(gate.get("cooldown_until_ms", 0))
    pass_since_ms = int(gate.get("pass_since_ms", 0))
    hold_ms_required = max(int(s_cfg.min_hold_seconds), 0) * 1000

    all_ok = (not stale_data) and cond_trades and cond_gap_p95 and cond_gap_max and cond_depth and cond_slippage and cond_spread and cond_vol
    if all_ok:
        if pass_since_ms <= 0:
            pass_since_ms = now
        gate["pass_since_ms"] = pass_since_ms
        if now < cooldown_until_ms:
            status = "WATCH"
            reason = "COOLDOWN"
        elif now - pass_since_ms < hold_ms_required:
            status = "WATCH"
            reason = "PASS_HOLD"
        else:
            status = "PASS"
            reason = "OK"
    else:
        gate["pass_since_ms"] = 0
        if critical:
            status = "REJECT"
            reason = "STALE_DATA" if stale_data else ("CRITICAL_" + ",".join(failed[:3]) if failed else "CRITICAL")
            gate["cooldown_until_ms"] = now + max(int(s_cfg.cooldown_seconds), 0) * 1000
        else:
            status = "WATCH"
            reason = "WATCH_" + ",".join(failed[:3]) if failed else "WATCH"

    state.set_pair_gate_state(symbol, gate)

    metrics: dict[str, float | int | bool | str] = {
        "symbol": symbol,
        "status": status,
        "reason": reason,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "median_spread_bps": median_spread_bps,
        "p25_spread_bps": p25_spread_bps,
        "p75_spread_bps": p75_spread_bps,
        "trades_per_min": trades_per_min,
        "median_trade_gap_ms": 0.0 if median_trade_gap_ms == float("inf") else median_trade_gap_ms,
        "p95_trade_gap_ms": 0.0 if p95_trade_gap_ms == float("inf") else p95_trade_gap_ms,
        "max_trade_gap_ms_window": 0.0 if max_trade_gap_ms_window == float("inf") else max_trade_gap_ms_window,
        "depth_bid_quote": depth_bid_quote,
        "depth_ask_quote": depth_ask_quote,
        "slippage_buy_bps": slippage_buy_bps,
        "slippage_sell_bps": slippage_sell_bps,
        "vol_1s_bps": vol_1s_bps,
        "p95_abs_move_1s_bps": p95_abs_move_1s_bps,
        "fee_entry_bps": fee_entry_bps,
        "fee_exit_bps": fee_exit_bps,
        "min_required_spread_bps": min_required_spread_bps,
        "stale_data": stale_data,
        "data_age_ms": data_age_ms,
        "book_age_ms": book_age_ms,
        "trade_age_ms": trade_age_ms,
    }

    state.set_pair_filter_snapshot(symbol, metrics)
    return PairAdmissionDecision(
        symbol=symbol,
        status=status,
        reason=reason,
        stale_data=stale_data,
        data_age_ms=data_age_ms,
        metrics=metrics,
    )
