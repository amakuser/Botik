from __future__ import annotations

import json
from pathlib import Path

from src.botik.gui.app import load_futures_training_workspace_read_model
from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, insert_model_stats, insert_signal_snapshot, upsert_outcome
from src.botik.storage.sqlite_store import get_connection, upsert_model_registry


def _seed_training_data(db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
        insert_signal_snapshot(
            conn,
            signal_id="sig-1",
            ts_signal_ms=1700000000000,
            symbol="ETHUSDT",
            side="Buy",
            best_bid=3000.0,
            best_ask=3000.5,
            mid=3000.25,
            spread_bps=1.6,
            depth_bid_quote=40000.0,
            depth_ask_quote=38000.0,
            slippage_buy_bps_est=1.0,
            slippage_sell_bps_est=1.0,
            trades_per_min=35.0,
            p95_trade_gap_ms=2200.0,
            vol_1s_bps=2.1,
            min_required_spread_bps=4.0,
            scanner_status="PASS",
            model_version="fut-model-v2",
            order_size_quote=25.0,
            order_size_base=0.008,
            entry_price=3000.25,
        )
        upsert_outcome(
            conn,
            signal_id="sig-1",
            symbol="ETHUSDT",
            entry_vwap=3000.2,
            exit_vwap=3012.0,
            filled_qty=0.008,
            hold_time_ms=120000,
            gross_pnl_quote=0.09,
            net_pnl_quote=0.07,
            net_edge_bps=6.2,
            max_adverse_excursion_bps=-2.4,
            max_favorable_excursion_bps=9.8,
            was_fully_filled=True,
            was_profitable=True,
            exit_reason="target",
        )
        upsert_model_registry(
            conn,
            model_id="fut-model-v1",
            path_or_payload="data/models/fut-model-v1.pkl",
            metrics_json=json.dumps({"quality_score": 0.62, "open_accuracy": 0.61, "training_loss": 0.39}),
            created_at_utc="2026-03-10T10:00:00Z",
            is_active=False,
        )
        upsert_model_registry(
            conn,
            model_id="fut-model-v2",
            path_or_payload="data/models/fut-model-v2.pkl",
            metrics_json=json.dumps(
                {"quality_score": 0.78, "open_accuracy": 0.75, "training_loss": 0.22, "val_loss": 0.28}
            ),
            created_at_utc="2026-03-11T11:00:00Z",
            is_active=True,
        )
        insert_model_stats(
            conn,
            model_id="fut-model-v2",
            ts_ms=1700000000000,
            net_edge_mean=4.4,
            win_rate=0.63,
            fill_rate=0.57,
        )
        insert_model_stats(
            conn,
            model_id="fut-model-v2",
            ts_ms=1700003600000,
            net_edge_mean=5.0,
            win_rate=0.66,
            fill_rate=0.60,
        )
    finally:
        conn.close()


def test_futures_training_workspace_read_model_collects_dataset_pipeline_and_checkpoints(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_training_read_model.db"
    _seed_training_data(db_path)

    read_model = load_futures_training_workspace_read_model(
        db_path,
        raw_cfg={
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "bybit": {"ws_public_host": "stream.bybit.com"},
            "strategy": {"runtime_strategy": "spike_reversal", "scanner_interval_sec": 3},
        },
        release_manifest={
            "active_futures_model_version": "fut-model-v2",
            "futures_training_engine_version": "0.1.1",
            "active_config_profile": "config.yaml",
        },
        ml_running=True,
        ml_paused=False,
        ml_process_state="running",
        training_mode="online",
    )
    assert read_model["training_runtime_status"] == "running"
    assert read_model["candles_source"] == "stream.bybit.com"
    assert read_model["dataset_prepared"] == "yes"
    assert int(read_model["dataset_rows"]) >= 1
    assert read_model["features_prepared"] == "yes"
    assert read_model["labels_prepared"] == "yes"
    assert read_model["active_symbol"] == "ETHUSDT"
    assert read_model["best_checkpoint"] == "fut-model-v2"
    assert read_model["latest_checkpoint"] == "fut-model-v2"
    assert read_model["active_futures_model_version"] == "fut-model-v2"
    assert read_model["training_engine_version"] == "0.1.1"
    assert len(read_model["checkpoints_rows"]) >= 2
    assert "open_accuracy" in str(read_model["evaluation_summary"])


def test_futures_training_workspace_read_model_safe_fallback_when_data_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_training_fallback.db"
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
    finally:
        conn.close()

    read_model = load_futures_training_workspace_read_model(
        db_path,
        raw_cfg={"symbols": ["BTCUSDT"]},
        release_manifest={},
        ml_running=False,
        ml_paused=False,
        ml_process_state="stopped",
        training_mode="bootstrap",
    )
    assert read_model["training_runtime_status"] == "idle"
    assert read_model["dataset_prepared"] == "no"
    assert read_model["features_prepared"] == "no"
    assert read_model["labels_prepared"] == "no"
    assert read_model["best_checkpoint"] == "not available"
    assert read_model["train_loss"] == "not available"
    assert read_model["val_loss"] == "not available"
    assert read_model["last_error"] == "not available"


def test_futures_training_workspace_read_model_exposes_training_actions_not_trading_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "futures_training_actions.db"
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
    finally:
        conn.close()
    read_model = load_futures_training_workspace_read_model(db_path)
    actions = [str(x).lower() for x in list(read_model.get("actions") or [])]
    assert "start training".lower() in actions
    assert "pause training".lower() in actions
    assert "run evaluation".lower() in actions
    assert "open checkpoints".lower() in actions
    assert all("long" not in action for action in actions)
    assert all("short" not in action for action in actions)
    assert all("start futures trading" not in action for action in actions)

    # Spot inventory fields must not leak into training workspace read model.
    assert "holdings_count" not in read_model
    assert "recovered_holdings_count" not in read_model
    assert "spot_workspace_holdings_rows" not in read_model
