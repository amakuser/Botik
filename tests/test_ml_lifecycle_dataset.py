from __future__ import annotations

import sqlite3
from pathlib import Path

from ml_service.dataset import FEATURE_NAMES, load_lifecycle_dataset
from src.botik.storage.lifecycle_store import (
    ensure_lifecycle_schema,
    insert_execution_event,
    insert_signal_snapshot,
    upsert_outcome,
)


def test_load_lifecycle_dataset_builds_labels_and_features(tmp_path: Path) -> None:
    db_path = tmp_path / "botik.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)

        insert_signal_snapshot(
            conn,
            signal_id="sig-1",
            ts_signal_ms=1_700_000_000_000,
            symbol="BTCUSDT",
            side="Buy",
            best_bid=100.0,
            best_ask=100.1,
            mid=100.05,
            spread_bps=10.0,
            depth_bid_quote=1000.0,
            depth_ask_quote=1100.0,
            slippage_buy_bps_est=0.3,
            slippage_sell_bps_est=0.2,
            trades_per_min=25.0,
            p95_trade_gap_ms=3000.0,
            vol_1s_bps=0.8,
            min_required_spread_bps=5.0,
            scanner_status="PASS",
            model_version="rules-v1",
            profile_id="safe",
            action_entry_tick_offset=1,
            action_order_qty_base=0.2,
            action_target_profit=0.0001,
            action_safety_buffer=0.0001,
            action_min_top_book_qty=1.0,
            action_stop_loss_pct=0.002,
            action_take_profit_pct=0.004,
            action_hold_timeout_sec=30,
            action_maker_only=True,
            order_size_quote=50.0,
            order_size_base=0.5,
            entry_price=100.0,
        )
        insert_execution_event(
            conn,
            exec_id="exec-1",
            order_id="ord-1",
            order_link_id="ol-1",
            signal_id="sig-1",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            exec_price=100.01,
            exec_qty=0.5,
            exec_fee=0.01,
            fee_rate=0.0008,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1_700_000_000_100,
        )
        upsert_outcome(
            conn,
            signal_id="sig-1",
            symbol="BTCUSDT",
            entry_vwap=100.01,
            exit_vwap=100.08,
            filled_qty=0.5,
            hold_time_ms=12_000,
            gross_pnl_quote=0.035,
            net_pnl_quote=0.03,
            net_edge_bps=6.5,
            max_adverse_excursion_bps=1.0,
            max_favorable_excursion_bps=3.0,
            was_fully_filled=True,
            was_profitable=True,
            exit_reason="take_profit",
        )

        insert_signal_snapshot(
            conn,
            signal_id="sig-2",
            ts_signal_ms=1_700_000_000_200,
            symbol="ETHUSDT",
            side="Sell",
            best_bid=200.0,
            best_ask=200.2,
            mid=200.1,
            spread_bps=10.0,
            depth_bid_quote=900.0,
            depth_ask_quote=800.0,
            slippage_buy_bps_est=0.5,
            slippage_sell_bps_est=0.4,
            trades_per_min=20.0,
            p95_trade_gap_ms=3500.0,
            vol_1s_bps=1.1,
            min_required_spread_bps=6.0,
            scanner_status="WATCH",
            model_version="rules-v1",
            profile_id="aggr",
            action_entry_tick_offset=2,
            action_order_qty_base=0.1,
            action_target_profit=0.0002,
            action_safety_buffer=0.0001,
            action_min_top_book_qty=1.0,
            action_stop_loss_pct=0.003,
            action_take_profit_pct=0.005,
            action_hold_timeout_sec=45,
            action_maker_only=True,
            order_size_quote=40.0,
            order_size_base=0.2,
            entry_price=200.0,
        )
        upsert_outcome(
            conn,
            signal_id="sig-2",
            symbol="ETHUSDT",
            entry_vwap=200.01,
            exit_vwap=200.0,
            filled_qty=0.2,
            hold_time_ms=20_000,
            gross_pnl_quote=-0.002,
            net_pnl_quote=-0.003,
            net_edge_bps=1.5,
            max_adverse_excursion_bps=2.0,
            max_favorable_excursion_bps=0.5,
            was_fully_filled=True,
            was_profitable=False,
            exit_reason="hold_timeout",
        )

        dataset = load_lifecycle_dataset(conn, target_edge_bps=4.0, limit=100, closed_only=True)
        assert dataset["X"].shape == (2, len(FEATURE_NAMES))
        assert dataset["y_open"].tolist() == [1, 0]
        assert dataset["y_fill"].tolist() == [1, 0]
        assert len(dataset["rows"]) == 2
    finally:
        conn.close()
