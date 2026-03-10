"""
Futures-specific risk state classification.
"""
from __future__ import annotations


BLOCKING_PROTECTION_STATUSES = {
    "pending",
    "repairing",
    "failed",
    "unprotected",
}


def normalize_protection_status(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_blocking_protection_status(value: str | None) -> bool:
    return normalize_protection_status(value) in BLOCKING_PROTECTION_STATUSES


def transition_protection_status(
    *,
    current_status: str | None,
    apply_attempted: bool,
    apply_success: bool,
    verify_status: str | None = None,
) -> str:
    """
    Minimal protection status state machine used by runtime:
      pending -> protected / unprotected / failed
      repairing -> protected / failed
    """
    current = normalize_protection_status(current_status)
    verified = normalize_protection_status(verify_status)
    if not apply_attempted:
        return current or "pending"
    if not apply_success:
        return "failed"
    if verified == "protected":
        return "protected"
    if verified == "closed":
        return "closed"
    if verified == "failed":
        return "failed"
    if verified == "unprotected":
        if current == "pending":
            return "unprotected"
        return "failed"
    return "failed"


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
