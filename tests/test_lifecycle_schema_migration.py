from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.storage.lifecycle_store import ensure_lifecycle_schema


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def test_lifecycle_schema_contains_action_and_reward_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "botik.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_lifecycle_schema(conn)
        signal_cols = _table_columns(conn, "signals")
        assert "profile_id" in signal_cols
        assert "action_entry_tick_offset" in signal_cols
        assert "action_order_qty_base" in signal_cols
        assert "action_target_profit" in signal_cols
        assert "action_safety_buffer" in signal_cols
        assert "action_min_top_book_qty" in signal_cols
        assert "action_stop_loss_pct" in signal_cols
        assert "action_take_profit_pct" in signal_cols
        assert "action_hold_timeout_sec" in signal_cols
        assert "action_maker_only" in signal_cols
        assert "policy_used" in signal_cols
        assert "pred_open_prob" in signal_cols
        assert "pred_exp_edge_bps" in signal_cols
        assert "active_model_id" in signal_cols
        assert "model_id" in signal_cols
        assert "reward_net_edge_bps" in signal_cols
        assert "reward_updated_at_utc" in signal_cols

        table_names = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "bandit_state" in table_names
        assert "model_stats" in table_names
    finally:
        conn.close()


def test_lifecycle_schema_migrates_existing_signals_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                ts_signal_ms INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        conn.commit()

        ensure_lifecycle_schema(conn)
        signal_cols = _table_columns(conn, "signals")
        assert "profile_id" in signal_cols
        assert "action_order_qty_base" in signal_cols
        assert "policy_used" in signal_cols
        assert "pred_open_prob" in signal_cols
        assert "model_id" in signal_cols
        assert "reward_net_edge_bps" in signal_cols
    finally:
        conn.close()
