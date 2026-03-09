"""
Futures-specific risk state classification.
"""
from __future__ import annotations


def classify_futures_state(
    *,
    protection_status: str,
    unrealized_pnl_pct: float | None = None,
    distance_to_liq_bps: float | None = None,
) -> str:
    status = str(protection_status or "").strip().lower()
    if status == "unprotected":
        return "unprotected_position"
    if status in {"failed", "repairing"}:
        return "soft_failure"
    if distance_to_liq_bps is not None and float(distance_to_liq_bps) <= 50.0:
        return "hard_failure"
    if unrealized_pnl_pct is None:
        return "unknown"
    pnl = float(unrealized_pnl_pct)
    if pnl <= -0.10:
        return "hard_failure"
    if pnl < -0.03:
        return "soft_failure"
    if pnl < 0:
        return "floating_loss"
    return "healthy"
