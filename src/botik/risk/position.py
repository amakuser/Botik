"""
Helpers for position accounting and unrealized PnL estimation.
"""
from __future__ import annotations


def apply_fill(
    current_qty: float,
    current_avg_entry: float,
    side: str,
    fill_qty: float,
    fill_price: float,
) -> tuple[float, float]:
    """
    Update signed position quantity and average entry price with a new fill.

    Quantity sign:
    - positive -> long
    - negative -> short
    """
    if fill_qty <= 0 or fill_price <= 0:
        return current_qty, current_avg_entry

    side_norm = side.lower()
    if side_norm not in {"buy", "sell"}:
        return current_qty, current_avg_entry

    signed_fill = fill_qty if side_norm == "buy" else -fill_qty
    if current_qty == 0:
        return signed_fill, fill_price

    same_direction = (current_qty > 0 and signed_fill > 0) or (current_qty < 0 and signed_fill < 0)
    if same_direction:
        new_qty = current_qty + signed_fill
        if new_qty == 0:
            return 0.0, 0.0
        new_avg = (abs(current_qty) * current_avg_entry + abs(signed_fill) * fill_price) / abs(new_qty)
        return new_qty, new_avg

    # Opposite direction: partial/full close or reversal.
    if abs(signed_fill) < abs(current_qty):
        return current_qty + signed_fill, current_avg_entry
    if abs(signed_fill) == abs(current_qty):
        return 0.0, 0.0
    return current_qty + signed_fill, fill_price


def unrealized_pnl_pct(position_qty: float, avg_entry_price: float, mark_price: float) -> float | None:
    if position_qty == 0 or avg_entry_price <= 0 or mark_price <= 0:
        return None
    if position_qty > 0:
        return (mark_price / avg_entry_price) - 1.0
    return (avg_entry_price / mark_price) - 1.0
