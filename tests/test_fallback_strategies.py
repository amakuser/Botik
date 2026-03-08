from __future__ import annotations

from src.botik.risk.exit_rules import decide_exit_reason


def test_fallback_stoploss_bps_triggers() -> None:
    reason, peak = decide_exit_reason(
        pnl_pct=-0.0012,  # -12 bps
        age_sec=5.0,
        hold_timeout_sec=60.0,
        pnl_exit_enabled=False,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        fallback_stoploss_bps=10.0,
        fallback_breakeven_bps=0.0,
        fallback_trailing_bps=0.0,
        fallback_trailing_activation_bps=0.0,
        peak_pnl_bps=0.0,
    )
    assert reason == "fallback_stoploss"
    assert peak <= 0.0


def test_fallback_breakeven_triggers_after_profit_and_return_to_zero() -> None:
    _, peak = decide_exit_reason(
        pnl_pct=0.0015,  # +15 bps
        age_sec=5.0,
        hold_timeout_sec=60.0,
        pnl_exit_enabled=False,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        fallback_stoploss_bps=0.0,
        fallback_breakeven_bps=10.0,
        fallback_trailing_bps=0.0,
        fallback_trailing_activation_bps=0.0,
        peak_pnl_bps=0.0,
    )
    reason, _ = decide_exit_reason(
        pnl_pct=0.0,
        age_sec=7.0,
        hold_timeout_sec=60.0,
        pnl_exit_enabled=False,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        fallback_stoploss_bps=0.0,
        fallback_breakeven_bps=10.0,
        fallback_trailing_bps=0.0,
        fallback_trailing_activation_bps=0.0,
        peak_pnl_bps=peak,
    )
    assert reason == "fallback_breakeven"


def test_fallback_trailing_triggers_after_peak_retrace() -> None:
    _, peak = decide_exit_reason(
        pnl_pct=0.0030,  # +30 bps
        age_sec=5.0,
        hold_timeout_sec=60.0,
        pnl_exit_enabled=False,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        fallback_stoploss_bps=0.0,
        fallback_breakeven_bps=0.0,
        fallback_trailing_bps=5.0,
        fallback_trailing_activation_bps=20.0,
        peak_pnl_bps=0.0,
    )
    reason, _ = decide_exit_reason(
        pnl_pct=0.0022,  # +22 bps (8 bps retrace from peak)
        age_sec=8.0,
        hold_timeout_sec=60.0,
        pnl_exit_enabled=False,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        fallback_stoploss_bps=0.0,
        fallback_breakeven_bps=0.0,
        fallback_trailing_bps=5.0,
        fallback_trailing_activation_bps=20.0,
        peak_pnl_bps=peak,
    )
    assert reason == "fallback_trailing"
