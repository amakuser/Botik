from __future__ import annotations

import sqlite3
from pathlib import Path

from ml_service.run_loop import run_autocalibration
from src.botik.storage.lifecycle_store import (
    ensure_lifecycle_schema,
    insert_execution_event,
    insert_signal_snapshot,
    upsert_outcome,
)


def test_run_autocalibration_writes_recommendations(tmp_path: Path) -> None:
    db_path = tmp_path / "botik.db"
    out_path = tmp_path / "autocalibration.json"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)
        for idx in range(25):
            signal_id = f"sig-{idx}"
            entry_price = 100.0 + idx * 0.01
            entry_vwap = entry_price * (1.0 + 0.0001)
            insert_signal_snapshot(
                conn,
                signal_id=signal_id,
                ts_signal_ms=1_700_000_000_000 + idx,
                symbol="BTCUSDT",
                side="Buy",
                best_bid=entry_price - 0.01,
                best_ask=entry_price + 0.01,
                mid=entry_price,
                spread_bps=2.0,
                depth_bid_quote=5000.0,
                depth_ask_quote=5000.0,
                slippage_buy_bps_est=0.5,
                slippage_sell_bps_est=0.5,
                trades_per_min=30.0,
                p95_trade_gap_ms=2500.0,
                vol_1s_bps=0.8,
                min_required_spread_bps=5.0,
                scanner_status="PASS",
                model_version="rules-v1",
                profile_id="safe",
                order_size_quote=50.0,
                order_size_base=0.5,
                entry_price=entry_price,
            )
            insert_execution_event(
                conn,
                exec_id=f"exec-{idx}",
                order_id=f"ord-{idx}",
                order_link_id=f"ol-{idx}",
                signal_id=signal_id,
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                exec_price=entry_vwap,
                exec_qty=0.5,
                exec_fee=0.01,
                fee_rate=0.0008,
                fee_currency="USDT",
                is_maker=True,
                exec_time_ms=1_700_000_000_100 + idx,
            )
            upsert_outcome(
                conn,
                signal_id=signal_id,
                symbol="BTCUSDT",
                entry_vwap=entry_vwap,
                exit_vwap=entry_vwap * 1.0002,
                filled_qty=0.5,
                hold_time_ms=10_000,
                gross_pnl_quote=0.01,
                net_pnl_quote=0.009,
                net_edge_bps=1.8,
                max_adverse_excursion_bps=0.4,
                max_favorable_excursion_bps=1.2,
                was_fully_filled=True,
                was_profitable=True,
                exit_reason="take_profit",
            )

        payload = run_autocalibration(
            conn,
            min_fills=20,
            safety_buffer_bps=2.0,
            target_edge_bps=4.0,
            out_path=out_path,
        )
        assert payload is not None
        assert out_path.exists()
        assert payload["sample_fills"] >= 20
        assert payload["fee_bps_median"] > 0
        assert payload["recommended_min_required_spread_bps"] > 0
    finally:
        conn.close()
