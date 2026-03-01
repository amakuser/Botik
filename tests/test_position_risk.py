"""Tests for position accounting helpers."""
from __future__ import annotations

import pytest

from src.botik.risk.position import apply_fill, unrealized_pnl_pct


def test_apply_fill_add_same_direction() -> None:
    qty, avg = apply_fill(1.0, 100.0, "Buy", 1.0, 110.0)
    assert qty == 2.0
    assert avg == 105.0


def test_apply_fill_partial_close_keeps_average() -> None:
    qty, avg = apply_fill(2.0, 100.0, "Sell", 0.5, 90.0)
    assert qty == 1.5
    assert avg == 100.0


def test_apply_fill_full_close_resets_position() -> None:
    qty, avg = apply_fill(1.5, 100.0, "Sell", 1.5, 90.0)
    assert qty == 0.0
    assert avg == 0.0


def test_apply_fill_reversal_sets_new_average() -> None:
    qty, avg = apply_fill(1.0, 100.0, "Sell", 1.5, 90.0)
    assert qty == -0.5
    assert avg == 90.0


def test_unrealized_pnl_pct_long_and_short() -> None:
    assert unrealized_pnl_pct(1.0, 100.0, 105.0) == pytest.approx(0.05)
    assert unrealized_pnl_pct(-1.0, 100.0, 95.0) > 0
