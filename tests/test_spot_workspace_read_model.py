from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import load_spot_workspace_read_model
from src.botik.storage.core_store import finish_reconciliation_run, start_reconciliation_run
from src.botik.storage.spot_store import (
    insert_spot_exit_decision,
    insert_spot_fill,
    upsert_spot_holding,
    upsert_spot_order,
)
from src.botik.storage.sqlite_store import get_connection


def _insert_holding(
    *,
    conn,
    symbol: str,
    hold_reason: str,
    recovered: bool,
    strategy_owner: str | None,
    auto_sell_allowed: bool,
    avg_entry_price: float | None = 1.0,
) -> None:
    upsert_spot_holding(
        conn,
        account_type="UNIFIED",
        symbol=symbol,
        base_asset=symbol.replace("USDT", ""),
        free_qty=1.0,
        locked_qty=0.0,
        avg_entry_price=avg_entry_price,
        hold_reason=hold_reason,
        source_of_truth="test",
        recovered_from_exchange=recovered,
        strategy_owner=strategy_owner,
        auto_sell_allowed=auto_sell_allowed,
    )


def test_spot_workspace_read_model_counts_and_classification(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_workspace.db"
    conn = get_connection(db_path)
    try:
        _insert_holding(
            conn=conn,
            symbol="BTCUSDT",
            hold_reason="strategy_entry",
            recovered=False,
            strategy_owner="spot_spread",
            auto_sell_allowed=False,
            avg_entry_price=60000.0,
        )
        _insert_holding(
            conn=conn,
            symbol="ETHUSDT",
            hold_reason="unknown_recovered_from_exchange",
            recovered=True,
            strategy_owner=None,
            auto_sell_allowed=False,
        )
        _insert_holding(
            conn=conn,
            symbol="DOGEUSDT",
            hold_reason="stale_hold",
            recovered=False,
            strategy_owner="spot_spread",
            auto_sell_allowed=False,
        )
        _insert_holding(
            conn=conn,
            symbol="XRPUSDT",
            hold_reason="manual_import",
            recovered=False,
            strategy_owner=None,
            auto_sell_allowed=False,
        )

        upsert_spot_order(
            conn,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Buy",
            status="New",
            price=60000.0,
            qty=0.01,
            order_id="order-1",
            order_link_id="link-1",
            order_type="Limit",
            time_in_force="PostOnly",
            strategy_owner="spot_spread",
        )
        upsert_spot_order(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Sell",
            status="Filled",
            price=3200.0,
            qty=0.2,
            order_id="order-2",
            order_link_id="link-2",
            order_type="Limit",
            time_in_force="GTC",
            strategy_owner="spot_spread",
        )
        insert_spot_fill(
            conn,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            side="Buy",
            exec_id="exec-1",
            order_id="order-1",
            order_link_id="link-1",
            price=60000.0,
            qty=0.01,
            fee=0.02,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1700000000123,
        )
        insert_spot_exit_decision(
            conn,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            decision_type="hold",
            reason="test",
            policy_name="spot-policy",
            pnl_pct=0.1,
            pnl_quote=1.23,
            applied=False,
        )
        run_id = start_reconciliation_run(conn, trigger_source="test")
        finish_reconciliation_run(conn, reconciliation_run_id=run_id, status="success", summary={"issues_created": 0})
    finally:
        conn.close()

    model = load_spot_workspace_read_model(db_path, account_type="UNIFIED", limit=200)
    assert model["holdings_count"] == 4
    assert model["recovered_holdings_count"] == 1
    assert model["stale_holdings_count"] == 1
    assert model["open_orders_count"] == 1
    assert len(model["open_orders_rows"]) == 1
    assert len(model["fills_rows"]) == 1
    assert len(model["exit_decisions_rows"]) == 1
    assert model["last_reconcile"] != "-"

    by_symbol = {str(row[1]): row for row in model["holdings_rows"]}
    assert by_symbol["BTCUSDT"][9] == "strategy_owned"
    assert by_symbol["BTCUSDT"][11] == "sell_allowed"
    assert by_symbol["ETHUSDT"][9] == "recovered_unknown"
    assert by_symbol["ETHUSDT"][11] == "protected_by_policy"
    assert by_symbol["DOGEUSDT"][9] == "stale_hold"
    assert by_symbol["DOGEUSDT"][13] == "yes"
    assert by_symbol["XRPUSDT"][9] == "manual_imported"
    assert by_symbol["XRPUSDT"][11] == "protected_by_policy"


def test_spot_workspace_read_model_safe_fallback_for_missing_optional_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_workspace_fallback.db"
    conn = get_connection(db_path)
    try:
        _insert_holding(
            conn=conn,
            symbol="SOLUSDT",
            hold_reason="strategy_entry",
            recovered=False,
            strategy_owner=None,
            auto_sell_allowed=False,
            avg_entry_price=None,
        )
    finally:
        conn.close()

    model = load_spot_workspace_read_model(db_path, account_type="UNIFIED", limit=50)
    assert model["holdings_count"] == 1
    row = model["holdings_rows"][0]
    assert row[5] == "unknown"  # avg_entry_price
    assert row[8] == "unknown"  # strategy_owner
    assert row[11] == "sell_allowed"  # strategy_entry class still allowed


def test_spot_workspace_read_model_does_not_expose_futures_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "spot_workspace_no_futures.db"
    conn = get_connection(db_path)
    try:
        _insert_holding(
            conn=conn,
            symbol="ADAUSDT",
            hold_reason="strategy_entry",
            recovered=False,
            strategy_owner="spot_spread",
            auto_sell_allowed=False,
        )
    finally:
        conn.close()

    model = load_spot_workspace_read_model(db_path, account_type="UNIFIED", limit=20)
    assert "futures_positions_rows" not in model
    assert "futures_open_orders_rows" not in model
    assert "futures_protection_line" not in model
