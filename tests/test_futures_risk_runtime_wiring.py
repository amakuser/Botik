from __future__ import annotations

from pathlib import Path

from src.botik.main import (
    evaluate_futures_symbol_risk,
    futures_entry_risk_gate,
    futures_force_exit_reason_from_risk_state,
)
from src.botik.storage.futures_store import upsert_futures_position
from src.botik.storage.spot_store import upsert_spot_holding
from src.botik.storage.sqlite_store import get_connection


def _upsert_futures_position(
    conn,
    *,
    symbol: str,
    side: str,
    qty: float,
    entry: float,
    mark: float,
    liq: float,
    protection_status: str,
) -> None:
    upsert_futures_position(
        conn,
        account_type="UNIFIED",
        symbol=symbol,
        side=side,
        position_idx=0,
        margin_mode="cross",
        leverage=5.0,
        qty=qty,
        entry_price=entry,
        mark_price=mark,
        liq_price=liq,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        take_profit=(entry * 1.01 if protection_status == "protected" else None),
        stop_loss=(entry * 0.99 if protection_status == "protected" else None),
        trailing_stop=None,
        protection_status=protection_status,
        strategy_owner="test",
        source_of_truth="test",
        recovered_from_exchange=False,
    )


def test_futures_entry_gate_blocks_unprotected_position(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_gate_unprotected.db"
    conn = get_connection(db_path)
    try:
        _upsert_futures_position(
            conn,
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
            entry=60000.0,
            mark=59950.0,
            liq=50000.0,
            protection_status="unprotected",
        )

        allowed, reason, risk_view = futures_entry_risk_gate(conn, symbol="BTCUSDT")
        assert allowed is False
        assert reason == "symbol_risk_state_unprotected_position"
        assert str(risk_view.get("risk_state")) == "unprotected_position"
    finally:
        conn.close()


def test_futures_entry_gate_blocks_hard_failure_when_liq_is_too_close(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_gate_hard_failure.db"
    conn = get_connection(db_path)
    try:
        # distance to liq ~= 40 bps for long position -> hard_failure by rules
        _upsert_futures_position(
            conn,
            symbol="ETHUSDT",
            side="Buy",
            qty=0.5,
            entry=3000.0,
            mark=3000.0,
            liq=2988.0,
            protection_status="protected",
        )

        risk_view = evaluate_futures_symbol_risk(conn, symbol="ETHUSDT")
        assert str(risk_view.get("risk_state")) == "hard_failure"
        assert float(risk_view.get("distance_to_liq_bps") or 0.0) <= 50.0

        allowed, reason, _ = futures_entry_risk_gate(conn, symbol="ETHUSDT")
        assert allowed is False
        assert reason == "symbol_risk_state_hard_failure"
    finally:
        conn.close()


def test_spot_domain_state_does_not_trigger_futures_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_not_futures_gate.db"
    conn = get_connection(db_path)
    try:
        upsert_spot_holding(
            conn,
            account_type="UNIFIED",
            symbol="ADAUSDT",
            base_asset="ADA",
            free_qty=100.0,
            locked_qty=0.0,
            avg_entry_price=0.5,
            hold_reason="strategy_entry",
            source_of_truth="test",
            recovered_from_exchange=False,
            strategy_owner="test",
            auto_sell_allowed=True,
        )

        allowed, reason, risk_view = futures_entry_risk_gate(conn, symbol="ADAUSDT")
        assert allowed is True
        assert reason == "ok"
        assert str(risk_view.get("risk_state")) == "unknown"
    finally:
        conn.close()


def test_futures_force_exit_reason_uses_futures_state_and_not_spot_defaults() -> None:
    assert (
        futures_force_exit_reason_from_risk_state(
            current_reason=None,
            risk_state="hard_failure",
        )
        == "futures_hard_failure"
    )
    assert (
        futures_force_exit_reason_from_risk_state(
            current_reason=None,
            risk_state="unprotected_position",
        )
        == "futures_unprotected_position"
    )
    # Existing explicit reason (for example, spot-like stop_loss) is preserved.
    assert (
        futures_force_exit_reason_from_risk_state(
            current_reason="stop_loss",
            risk_state="hard_failure",
        )
        == "stop_loss"
    )
