"""
Spot-specific risk helpers.
"""
from __future__ import annotations


PROTECTED_HOLD_REASONS = {
    "manual_import",
    "unknown_recovered_from_exchange",
}


def can_auto_sell_hold(
    *,
    hold_reason: str,
    auto_sell_allowed: bool,
) -> bool:
    reason = str(hold_reason or "").strip()
    if auto_sell_allowed:
        return True
    return reason not in PROTECTED_HOLD_REASONS


def classify_spot_state(
    *,
    hold_reason: str,
    pnl_pct: float | None,
) -> str:
    reason = str(hold_reason or "").strip()
    if reason == "stale_hold":
        return "stale_hold"
    if reason == "unknown_recovered_from_exchange":
        return "recovered_hold"
    if pnl_pct is None:
        return "unknown"
    if pnl_pct < 0:
        return "floating_loss"
    if pnl_pct > 0:
        return "floating_profit"
    return "flat"
