from __future__ import annotations

import sqlite3
from pathlib import Path

from ml_service.run_loop import _compute_training_metrics, _count_closed_signals, _is_training_paused
from src.botik.storage.lifecycle_store import (
    ensure_lifecycle_schema,
    insert_execution_event,
    insert_signal_snapshot,
    upsert_outcome,
)


def test_compute_training_metrics_and_pause_flag(tmp_path: Path) -> None:
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
            depth_ask_quote=1000.0,
            slippage_buy_bps_est=0.2,
            slippage_sell_bps_est=0.2,
            trades_per_min=20.0,
            p95_trade_gap_ms=3000.0,
            vol_1s_bps=1.0,
            min_required_spread_bps=5.0,
            scanner_status="PASS",
            model_version="v1",
            profile_id="safe",
            order_size_quote=50.0,
            order_size_base=0.5,
            entry_price=100.0,
        )
        insert_execution_event(
            conn,
            exec_id="e-1",
            order_id="o-1",
            order_link_id="ol-1",
            signal_id="sig-1",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            exec_price=100.0,
            exec_qty=0.5,
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
            exit_vwap=100.2,
            filled_qty=0.5,
            hold_time_ms=15000,
            gross_pnl_quote=0.1,
            net_pnl_quote=0.09,
            net_edge_bps=4.0,
            max_adverse_excursion_bps=0.5,
            max_favorable_excursion_bps=1.1,
            was_fully_filled=True,
            was_profitable=True,
            exit_reason="tp",
        )

        metrics = _compute_training_metrics(conn, window=20)
        assert metrics["net_edge_mean"] >= 4.0
        assert metrics["win_rate"] == 1.0
        assert metrics["fill_rate"] == 1.0
        assert _count_closed_signals(conn) == 1
    finally:
        conn.close()

    pause_flag = tmp_path / "training.paused"
    assert _is_training_paused(pause_flag) is False
    pause_flag.write_text("paused\n", encoding="utf-8")
    assert _is_training_paused(pause_flag) is True
