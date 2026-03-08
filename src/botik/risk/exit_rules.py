"""
Fallback exit decision helpers (break-even / stop-loss / trailing).
"""
from __future__ import annotations


def decide_exit_reason(
    *,
    pnl_pct: float | None,
    age_sec: float,
    hold_timeout_sec: float,
    pnl_exit_enabled: bool,
    stop_loss_pct: float,
    take_profit_pct: float,
    fallback_stoploss_bps: float,
    fallback_breakeven_bps: float,
    fallback_trailing_bps: float,
    fallback_trailing_activation_bps: float,
    peak_pnl_bps: float,
) -> tuple[str | None, float]:
    """
    Return (reason, updated_peak_pnl_bps).
    """
    peak = float(peak_pnl_bps)
    pnl_bps: float | None = None
    if pnl_pct is not None:
        pnl_bps = float(pnl_pct) * 10000.0
        if pnl_bps > peak:
            peak = pnl_bps

    reason: str | None = None
    if pnl_exit_enabled and pnl_pct is not None:
        if stop_loss_pct > 0 and pnl_pct <= -stop_loss_pct:
            reason = "stop_loss"
        elif take_profit_pct > 0 and pnl_pct >= take_profit_pct:
            reason = "take_profit"

    if reason is None and pnl_bps is not None:
        if fallback_stoploss_bps > 0 and pnl_bps <= -abs(fallback_stoploss_bps):
            reason = "fallback_stoploss"
        elif fallback_breakeven_bps > 0 and peak >= fallback_breakeven_bps and pnl_bps <= 0:
            reason = "fallback_breakeven"
        elif (
            fallback_trailing_bps > 0
            and peak >= max(float(fallback_trailing_activation_bps), 0.0)
            and pnl_bps <= peak - abs(fallback_trailing_bps)
        ):
            reason = "fallback_trailing"

    if reason is None and age_sec >= hold_timeout_sec:
        reason = "hold_timeout"

    return reason, peak
