from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import load_futures_paper_workspace_read_model
from src.botik.storage.futures_store import upsert_futures_open_order, upsert_futures_position
from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, insert_signal_snapshot, upsert_outcome
from src.botik.storage.sqlite_store import get_connection


def _seed_futures_paper_workspace(db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
        upsert_futures_position(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            side="Buy",
            position_idx=1,
            margin_mode="cross",
            leverage=5.0,
            qty=0.02,
            entry_price=3000.0,
            mark_price=3010.5,
            liq_price=2500.0,
            unrealized_pnl=0.21,
            realized_pnl=None,
            take_profit=3050.0,
            stop_loss=2950.0,
            trailing_stop=None,
            protection_status="protected",
            strategy_owner="futures_paper",
            source_of_truth="paper_session",
            recovered_from_exchange=False,
        )
        upsert_futures_open_order(
            conn,
            account_type="UNIFIED",
            symbol="ETHUSDT",
            status="New",
            order_link_id="paper-order-1",
            order_id="paper-order-1",
            side="Sell",
            order_type="Limit",
            time_in_force="GTC",
            price=3045.0,
            qty=0.02,
            reduce_only=True,
            close_on_trigger=False,
            strategy_owner="futures_paper",
        )
        insert_signal_snapshot(
            conn,
            signal_id="paper-good",
            ts_signal_ms=1700000000000,
            symbol="ETHUSDT",
            side="Buy",
            best_bid=3000.0,
            best_ask=3000.5,
            mid=3000.25,
            spread_bps=1.5,
            depth_bid_quote=20000.0,
            depth_ask_quote=21000.0,
            slippage_buy_bps_est=1.0,
            slippage_sell_bps_est=1.0,
            trades_per_min=30.0,
            p95_trade_gap_ms=2000.0,
            vol_1s_bps=2.0,
            min_required_spread_bps=4.0,
            scanner_status="PASS",
            model_version="fut-paper-v2",
            policy_used="hybrid",
            active_model_id="fut-paper-v2",
            model_id="fut-paper-v2",
            entry_price=3000.25,
        )
        upsert_outcome(
            conn,
            signal_id="paper-good",
            symbol="ETHUSDT",
            entry_vwap=3000.25,
            exit_vwap=3012.0,
            filled_qty=0.02,
            hold_time_ms=90000,
            gross_pnl_quote=0.30,
            net_pnl_quote=0.24,
            net_edge_bps=6.1,
            max_adverse_excursion_bps=-4.0,
            max_favorable_excursion_bps=10.0,
            was_fully_filled=True,
            was_profitable=False,
            exit_reason="paper_target",
        )
        conn.execute("UPDATE outcomes SET closed_at_utc=? WHERE signal_id=?", ("2026-03-14T10:15:00Z", "paper-good"))

        insert_signal_snapshot(
            conn,
            signal_id="paper-bad",
            ts_signal_ms=1700003600000,
            symbol="BTCUSDT",
            side="Sell",
            best_bid=64000.0,
            best_ask=64000.5,
            mid=64000.25,
            spread_bps=1.0,
            depth_bid_quote=30000.0,
            depth_ask_quote=29000.0,
            slippage_buy_bps_est=0.8,
            slippage_sell_bps_est=0.8,
            trades_per_min=18.0,
            p95_trade_gap_ms=3100.0,
            vol_1s_bps=1.7,
            min_required_spread_bps=3.0,
            scanner_status="PASS",
            model_version="fut-paper-v1",
            policy_used="hard_rules",
            active_model_id="",
            model_id="",
            entry_price=64000.25,
        )
        upsert_outcome(
            conn,
            signal_id="paper-bad",
            symbol="BTCUSDT",
            entry_vwap=64000.25,
            exit_vwap=64110.0,
            filled_qty=0.01,
            hold_time_ms=120000,
            gross_pnl_quote=-0.40,
            net_pnl_quote=-0.44,
            net_edge_bps=-7.2,
            max_adverse_excursion_bps=-12.0,
            max_favorable_excursion_bps=3.0,
            was_fully_filled=True,
            was_profitable=True,
            exit_reason="paper_stop",
        )
        conn.execute("UPDATE outcomes SET closed_at_utc=? WHERE signal_id=?", ("2026-03-14T10:20:00Z", "paper-bad"))
        conn.commit()
    finally:
        conn.close()


def test_futures_paper_workspace_read_model_builds_positions_orders_and_closed_results(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_paper_workspace.db"
    _seed_futures_paper_workspace(db_path)

    read_model = load_futures_paper_workspace_read_model(
        db_path,
        release_manifest={"active_futures_model_version": "fut-paper-v2"},
    )

    assert read_model["positions_count"] == 1
    assert read_model["open_orders_count"] == 1
    assert read_model["closed_results_count"] == 2
    assert read_model["good_results_count"] == 1
    assert read_model["bad_results_count"] == 1
    assert read_model["flat_results_count"] == 0
    assert round(float(read_model["net_pnl_total"]), 6) == -0.20
    assert "read_only" in str(read_model["summary_line"])
    assert "close_controls=unsupported" in str(read_model["status_line"])

    by_signal_symbol = {(str(row[1]), str(row[10])): row for row in list(read_model["closed_results_rows"])}
    good_row = by_signal_symbol[("ETHUSDT", "2026-03-14T10:15:00Z")]
    bad_row = by_signal_symbol[("BTCUSDT", "2026-03-14T10:20:00Z")]
    assert good_row[6] == "good"
    assert good_row[7] == "fut-paper-v2"
    assert bad_row[6] == "bad"
    assert bad_row[7] == "unknown"


def test_futures_paper_workspace_read_model_exposes_paper_actions_not_trading_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_paper_actions.db"
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
    finally:
        conn.close()

    read_model = load_futures_paper_workspace_read_model(db_path)
    actions = [str(x).lower() for x in list(read_model.get("actions") or [])]
    assert "close selected paper position" in actions
    assert "close all paper positions" in actions
    assert "reset paper session" in actions
    assert "open futures logs" in actions
    assert all("long" not in action for action in actions)
    assert all("short" not in action for action in actions)
    assert all("start futures trading" not in action for action in actions)
    assert "holdings_count" not in read_model
    assert "spot_workspace_holdings_rows" not in read_model
    assert "training_runtime_status" not in read_model


def test_futures_paper_workspace_read_model_safe_fallback_when_data_missing(tmp_path: Path) -> None:
    read_model = load_futures_paper_workspace_read_model(
        tmp_path / "missing_futures_paper.db",
        release_manifest={"active_futures_model_version": "paper-fallback"},
    )
    assert read_model["positions_count"] == 0
    assert read_model["open_orders_count"] == 0
    assert read_model["closed_results_count"] == 0
    assert read_model["active_futures_model_version"] == "paper-fallback"
    assert read_model["closed_results_rows"] == []
    assert "paper_session=read_only" in str(read_model["summary_line"])
