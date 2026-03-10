from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import load_runtime_ops_status_snapshot, runtime_capabilities_for_mode
from src.botik.storage.core_store import finish_reconciliation_run, insert_reconciliation_issue, start_reconciliation_run
from src.botik.storage.futures_store import (
    insert_futures_funding_event,
    insert_futures_liquidation_risk_snapshot,
    upsert_futures_open_order,
    upsert_futures_position,
)
from src.botik.storage.spot_store import upsert_spot_holding
from src.botik.storage.sqlite_store import get_connection


def test_load_runtime_ops_status_snapshot_reports_freshness_and_reconciliation(tmp_path: Path) -> None:
    db_path = tmp_path / "gui_ops_status.db"
    conn = get_connection(db_path)
    try:
        upsert_spot_holding(
            conn,
            account_type="UNIFIED",
            symbol="BTCUSDT",
            base_asset="BTC",
            free_qty=0.1,
            locked_qty=0.0,
            avg_entry_price=60000.0,
            hold_reason="strategy_entry",
            source_of_truth="test",
            recovered_from_exchange=False,
            strategy_owner="test",
            auto_sell_allowed=True,
        )
        upsert_futures_position(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            margin_mode="cross",
            leverage=3.0,
            qty=0.2,
            entry_price=3000.0,
            mark_price=3010.0,
            liq_price=2500.0,
            unrealized_pnl=2.0,
            realized_pnl=0.0,
            take_profit=3060.0,
            stop_loss=2970.0,
            trailing_stop=None,
            protection_status="pending",
            strategy_owner="test",
            source_of_truth="test",
            recovered_from_exchange=False,
        )
        upsert_futures_open_order(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            status="New",
            order_link_id="fut-link-1",
            order_id="fut-order-1",
            side="Sell",
            order_type="Limit",
            time_in_force="PostOnly",
            price=3050.0,
            qty=0.2,
            reduce_only=True,
            strategy_owner="test",
        )
        insert_futures_funding_event(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            funding_rate=0.0001,
            funding_fee=-0.12,
            funding_time_ms=1700000001000,
        )
        insert_futures_liquidation_risk_snapshot(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=0,
            mark_price=3010.0,
            liq_price=2500.0,
            distance_to_liq_bps=1694.35,
            payload={"source": "test"},
        )

        run_id = start_reconciliation_run(conn, trigger_source="startup")
        insert_reconciliation_issue(
            conn,
            issue_type="orphaned_exchange_order",
            domain="futures",
            severity="warning",
            symbol="ETHUSDT",
            details={"source": "test"},
            reconciliation_run_id=run_id,
            status="open",
        )
        finish_reconciliation_run(
            conn,
            reconciliation_run_id=run_id,
            status="success",
            summary={"issues_created": 1},
        )
    finally:
        conn.close()

    snapshot = load_runtime_ops_status_snapshot(db_path)
    assert snapshot["spot_holdings_freshness"] != "-"
    assert snapshot["futures_positions_freshness"] != "-"
    assert snapshot["futures_orders_freshness"] != "-"
    assert snapshot["reconciliation_issues_freshness"] != "-"
    assert snapshot["futures_funding_freshness"] != "-"
    assert snapshot["futures_liq_snapshots_freshness"] != "-"
    assert snapshot["reconciliation_last_status"] == "success"
    assert snapshot["reconciliation_last_trigger"] == "startup"
    assert str(snapshot["futures_protection_line"]).find("pending=1") >= 0
    assert str(snapshot["futures_risk_telemetry_line"]).find("funding=ETHUSDT") >= 0
    assert str(snapshot["futures_risk_telemetry_line"]).find("liq=ETHUSDT") >= 0


def test_runtime_capabilities_for_mode_reports_paper_as_unsupported() -> None:
    paper = runtime_capabilities_for_mode("paper")
    assert paper["reconciliation"] == "unsupported"
    assert paper["protection"] == "unsupported"

    live = runtime_capabilities_for_mode("live")
    assert live["reconciliation"] == "supported"
    assert live["protection"] == "supported"


def test_load_runtime_ops_status_snapshot_reports_issue_counts_and_lock_symbols(tmp_path: Path) -> None:
    db_path = tmp_path / "gui_ops_issue_counts.db"
    conn = get_connection(db_path)
    try:
        insert_reconciliation_issue(
            conn,
            issue_type="orphaned_exchange_order",
            domain="futures",
            severity="warning",
            symbol="BTCUSDT",
            details={"source": "test"},
            status="open",
        )
        insert_reconciliation_issue(
            conn,
            issue_type="local_position_missing_on_exchange",
            domain="futures",
            severity="warning",
            symbol="ETHUSDT",
            details={"source": "test"},
            status="resolved",
        )
    finally:
        conn.close()

    snapshot = load_runtime_ops_status_snapshot(db_path)
    assert int(snapshot["reconciliation_open_issues"]) == 1
    assert int(snapshot["reconciliation_resolved_issues"]) >= 1
    assert "BTCUSDT" in list(snapshot["reconciliation_lock_symbols"])
    assert "ETHUSDT" not in list(snapshot["reconciliation_lock_symbols"])
