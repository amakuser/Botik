"""
Helpers for futures protection planning and entry gate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuturesProtectionPlan:
    stop_loss: float
    take_profit: float
    trailing_stop: float | None
    stop_loss_pct: float
    take_profit_pct: float


def validate_futures_protection_params(
    *,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> tuple[bool, str]:
    sl = float(stop_loss_pct or 0.0)
    tp = float(take_profit_pct or 0.0)
    if sl <= 0:
        return False, "missing_stop_loss"
    if tp <= 0:
        return False, "missing_take_profit"
    return True, "ok"


def build_futures_protection_plan(
    *,
    entry_price: float,
    position_qty: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    trailing_stop: float | None = None,
) -> FuturesProtectionPlan | None:
    if entry_price <= 0 or position_qty == 0:
        return None
    is_valid, _ = validate_futures_protection_params(
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    if not is_valid:
        return None

    sl = float(stop_loss_pct)
    tp = float(take_profit_pct)
    if position_qty > 0:
        stop_loss = entry_price * (1.0 - sl)
        take_profit = entry_price * (1.0 + tp)
    else:
        stop_loss = entry_price * (1.0 + sl)
        take_profit = entry_price * (1.0 - tp)
    if stop_loss <= 0 or take_profit <= 0:
        return None
    return FuturesProtectionPlan(
        stop_loss=float(stop_loss),
        take_profit=float(take_profit),
        trailing_stop=(float(trailing_stop) if trailing_stop is not None else None),
        stop_loss_pct=sl,
        take_profit_pct=tp,
    )


def futures_entry_allowed(
    *,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
    has_unprotected_position: bool,
) -> tuple[bool, str]:
    valid, reason = validate_futures_protection_params(
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    if not valid:
        return False, reason
    if has_unprotected_position:
        return False, "symbol_has_unprotected_position"
    return True, "ok"
