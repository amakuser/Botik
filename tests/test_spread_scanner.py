"""Tests for spread scanner math and filters."""
from __future__ import annotations

from src.botik.strategy.spread_scanner import compute_net_edge, scan_spread


def test_compute_net_edge_formula() -> None:
    entry = 100.0
    exit_ = 101.0
    buy_fee = 0.001
    sell_fee = 0.001
    expected = ((exit_ * (1 - sell_fee)) / (entry * (1 + buy_fee))) - 1
    assert abs(compute_net_edge(entry, exit_, buy_fee, sell_fee) - expected) < 1e-12


def test_scan_rejects_low_liquidity() -> None:
    result = scan_spread(
        best_bid=100.0,
        best_ask=101.0,
        best_bid_size=0.01,
        best_ask_size=0.01,
        tick_size=0.01,
        entry_tick_offset=1,
        buy_fee=0.0,
        sell_fee=0.0,
        target_profit=0.0,
        safety_buffer=0.0,
        min_top_book_qty=1.0,
    )
    assert result.tradable is False
    assert result.reason == "top_book_liquidity_too_low"


def test_scan_tradable_when_edge_above_threshold() -> None:
    result = scan_spread(
        best_bid=100.0,
        best_ask=101.5,
        best_bid_size=10.0,
        best_ask_size=10.0,
        tick_size=0.01,
        entry_tick_offset=1,
        buy_fee=0.0,
        sell_fee=0.0,
        target_profit=0.001,
        safety_buffer=0.001,
        min_top_book_qty=1.0,
    )
    assert result.tradable is True
    assert result.reason == "ok"
    assert result.net_edge > result.required_edge
