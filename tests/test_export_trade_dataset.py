from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.botik.storage.lifecycle_store import (
    ensure_lifecycle_schema,
    insert_execution_event,
    insert_signal_snapshot,
    upsert_outcome,
)
from tools.export_trade_dataset import export_dataset


EXPECTED_EXPORT_COLUMNS = [
    "signal_id",
    "symbol",
    "side",
    "ts_signal_ms",
    "spread_bps_at_signal",
    "depth_bid_quote_at_signal",
    "depth_ask_quote_at_signal",
    "slippage_buy_bps_est",
    "slippage_sell_bps_est",
    "trades_per_min_at_signal",
    "p95_trade_gap_ms_at_signal",
    "vol_1s_bps_at_signal",
    "min_required_spread_bps",
    "policy_used",
    "profile_id",
    "order_notional_quote",
    "entry_vwap",
    "exit_vwap",
    "total_exec_qty",
    "total_fees_quote",
    "net_pnl_quote",
    "net_edge_bps",
    "label_open",
    "label_fill",
]


def test_export_dataset_labels_from_net_edge_and_fills(tmp_path: Path) -> None:
    db_path = tmp_path / "botik.db"
    out_csv = tmp_path / "dataset.csv"

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
            depth_bid_quote=10000.0,
            depth_ask_quote=10000.0,
            slippage_buy_bps_est=0.2,
            slippage_sell_bps_est=0.3,
            trades_per_min=50.0,
            p95_trade_gap_ms=1200.0,
            vol_1s_bps=1.0,
            min_required_spread_bps=5.0,
            scanner_status="PASS",
            model_version="rules-v1",
            profile_id="aggr",
            action_entry_tick_offset=1,
            action_order_qty_base=0.5,
            action_target_profit=0.0002,
            action_safety_buffer=0.0001,
            action_min_top_book_qty=1.0,
            action_stop_loss_pct=0.003,
            action_take_profit_pct=0.005,
            action_hold_timeout_sec=30,
            action_maker_only=True,
            order_size_quote=50.0,
            order_size_base=2.0,
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
            exec_price=100.0,
            exec_qty=1.0,
            exec_fee=0.01,
            fee_rate=0.0001,
            fee_currency="USDT",
            is_maker=True,
            exec_time_ms=1_700_000_000_100,
        )
        upsert_outcome(
            conn,
            signal_id="sig-1",
            symbol="BTCUSDT",
            entry_vwap=100.0,
            exit_vwap=100.3,
            filled_qty=1.0,
            hold_time_ms=15_000,
            gross_pnl_quote=0.30,
            net_pnl_quote=0.29,
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
            side="Buy",
            best_bid=200.0,
            best_ask=200.2,
            mid=200.1,
            spread_bps=10.0,
            depth_bid_quote=8000.0,
            depth_ask_quote=9000.0,
            slippage_buy_bps_est=0.3,
            slippage_sell_bps_est=0.4,
            trades_per_min=25.0,
            p95_trade_gap_ms=3500.0,
            vol_1s_bps=1.5,
            min_required_spread_bps=6.0,
            scanner_status="WATCH",
            model_version="rules-v1",
            profile_id="safe",
            action_entry_tick_offset=2,
            action_order_qty_base=0.2,
            action_target_profit=0.0001,
            action_safety_buffer=0.0001,
            action_min_top_book_qty=2.0,
            action_stop_loss_pct=0.002,
            action_take_profit_pct=0.004,
            action_hold_timeout_sec=20,
            action_maker_only=True,
            order_size_quote=40.0,
            order_size_base=1.0,
            entry_price=200.0,
        )
    finally:
        conn.close()

    rows = export_dataset(db_path=db_path, out_csv=out_csv, out_parquet=None, target_edge_bps=4.0)
    assert rows == 2

    with out_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == EXPECTED_EXPORT_COLUMNS
        exported = list(reader)

    by_signal = {row["signal_id"]: row for row in exported}
    assert by_signal["sig-1"]["label_fill"] == "1"
    assert by_signal["sig-1"]["label_open"] == "1"
    assert by_signal["sig-1"]["policy_used"] in {"", "None"}
    assert by_signal["sig-1"]["profile_id"] == "aggr"
    assert by_signal["sig-1"]["total_exec_qty"] == "1.0"
    assert by_signal["sig-1"]["order_notional_quote"] == "50.0"
    assert by_signal["sig-1"]["net_edge_bps"] == "6.5"

    assert by_signal["sig-2"]["label_fill"] == "0"
    assert by_signal["sig-2"]["label_open"] == "0"
    assert by_signal["sig-2"]["profile_id"] == "safe"
