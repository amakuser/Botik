from __future__ import annotations

from src.botik.risk.futures_protection import (
    build_futures_protection_plan,
    futures_entry_allowed,
    validate_futures_protection_params,
)


def test_validate_futures_protection_params_rejects_missing_values() -> None:
    ok, reason = validate_futures_protection_params(stop_loss_pct=0.0, take_profit_pct=0.01)
    assert ok is False
    assert reason == "missing_stop_loss"

    ok, reason = validate_futures_protection_params(stop_loss_pct=0.01, take_profit_pct=0.0)
    assert ok is False
    assert reason == "missing_take_profit"

    ok, reason = validate_futures_protection_params(stop_loss_pct=0.01, take_profit_pct=0.02)
    assert ok is True
    assert reason == "ok"


def test_build_futures_protection_plan_for_long_and_short() -> None:
    long_plan = build_futures_protection_plan(
        entry_price=100.0,
        position_qty=1.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
    )
    assert long_plan is not None
    assert abs(long_plan.stop_loss - 98.0) < 1e-9
    assert abs(long_plan.take_profit - 104.0) < 1e-9

    short_plan = build_futures_protection_plan(
        entry_price=100.0,
        position_qty=-1.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
    )
    assert short_plan is not None
    assert abs(short_plan.stop_loss - 102.0) < 1e-9
    assert abs(short_plan.take_profit - 96.0) < 1e-9


def test_futures_entry_allowed_rejects_symbol_with_unprotected_position() -> None:
    ok, reason = futures_entry_allowed(
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
        has_unprotected_position=True,
    )
    assert ok is False
    assert reason == "symbol_has_unprotected_position"
