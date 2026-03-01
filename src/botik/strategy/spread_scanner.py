"""
Spread scanner helpers for maker-style spot quoting.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpreadScanResult:
    tradable: bool
    reason: str
    entry_price: float
    exit_price: float
    net_edge: float
    required_edge: float


def compute_net_edge(
    entry_price: float,
    exit_price: float,
    buy_fee: float,
    sell_fee: float,
) -> float:
    """
    net_edge = ((exit_price * (1 - sell_fee)) / (entry_price * (1 + buy_fee))) - 1
    """
    if entry_price <= 0 or exit_price <= 0:
        return -1.0
    denominator = entry_price * (1.0 + max(buy_fee, 0.0))
    if denominator <= 0:
        return -1.0
    numerator = exit_price * (1.0 - max(sell_fee, 0.0))
    return (numerator / denominator) - 1.0


def scan_spread(
    best_bid: float,
    best_ask: float,
    best_bid_size: float,
    best_ask_size: float,
    tick_size: float,
    entry_tick_offset: int,
    buy_fee: float,
    sell_fee: float,
    target_profit: float,
    safety_buffer: float,
    min_top_book_qty: float,
) -> SpreadScanResult:
    if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
        return SpreadScanResult(
            tradable=False,
            reason="invalid_top_of_book",
            entry_price=0.0,
            exit_price=0.0,
            net_edge=-1.0,
            required_edge=target_profit + safety_buffer,
        )

    tick = max(tick_size, 0.0) * max(entry_tick_offset, 1)
    entry_price = best_bid + tick
    exit_price = best_ask - tick
    required_edge = target_profit + safety_buffer

    if min_top_book_qty > 0:
        if best_bid_size < min_top_book_qty or best_ask_size < min_top_book_qty:
            return SpreadScanResult(
                tradable=False,
                reason="top_book_liquidity_too_low",
                entry_price=entry_price,
                exit_price=exit_price,
                net_edge=-1.0,
                required_edge=required_edge,
            )

    if entry_price <= 0 or exit_price <= 0 or exit_price <= entry_price:
        return SpreadScanResult(
            tradable=False,
            reason="invalid_entry_exit_after_tick",
            entry_price=entry_price,
            exit_price=exit_price,
            net_edge=-1.0,
            required_edge=required_edge,
        )

    net_edge = compute_net_edge(
        entry_price=entry_price,
        exit_price=exit_price,
        buy_fee=buy_fee,
        sell_fee=sell_fee,
    )
    return SpreadScanResult(
        tradable=net_edge > required_edge,
        reason="ok" if net_edge > required_edge else "net_edge_below_threshold",
        entry_price=entry_price,
        exit_price=exit_price,
        net_edge=net_edge,
        required_edge=required_edge,
    )
