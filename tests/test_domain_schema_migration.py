from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.storage.sqlite_store import get_connection


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def test_domain_tables_are_created_additively(tmp_path: Path) -> None:
    db_path = tmp_path / "botik_domain.db"
    conn = get_connection(db_path)
    try:
        names = _table_names(conn)
        assert "account_snapshots" in names
        assert "reconciliation_runs" in names
        assert "reconciliation_issues" in names
        assert "strategy_runs" in names
        assert "events_audit" in names

        assert "spot_balances" in names
        assert "spot_holdings" in names
        assert "spot_orders" in names
        assert "spot_fills" in names
        assert "spot_position_intents" in names
        assert "spot_exit_decisions" in names

        assert "futures_positions" in names
        assert "futures_open_orders" in names
        assert "futures_fills" in names
        assert "futures_protection_orders" in names
        assert "futures_funding_events" in names
        assert "futures_liquidation_risk_snapshots" in names
        assert "futures_position_decisions" in names
    finally:
        conn.close()


def test_required_columns_present_for_holdings_and_positions(tmp_path: Path) -> None:
    db_path = tmp_path / "botik_domain_columns.db"
    conn = get_connection(db_path)
    try:
        spot_cols = _table_columns(conn, "spot_holdings")
        assert "account_type" in spot_cols
        assert "symbol" in spot_cols
        assert "base_asset" in spot_cols
        assert "free_qty" in spot_cols
        assert "locked_qty" in spot_cols
        assert "avg_entry_price" in spot_cols
        assert "hold_reason" in spot_cols
        assert "source_of_truth" in spot_cols
        assert "recovered_from_exchange" in spot_cols
        assert "strategy_owner" in spot_cols
        assert "created_at_utc" in spot_cols
        assert "updated_at_utc" in spot_cols

        fut_cols = _table_columns(conn, "futures_positions")
        assert "account_type" in fut_cols
        assert "symbol" in fut_cols
        assert "side" in fut_cols
        assert "position_idx" in fut_cols
        assert "margin_mode" in fut_cols
        assert "leverage" in fut_cols
        assert "qty" in fut_cols
        assert "entry_price" in fut_cols
        assert "mark_price" in fut_cols
        assert "liq_price" in fut_cols
        assert "unrealized_pnl" in fut_cols
        assert "realized_pnl" in fut_cols
        assert "take_profit" in fut_cols
        assert "stop_loss" in fut_cols
        assert "trailing_stop" in fut_cols
        assert "protection_status" in fut_cols
        assert "strategy_owner" in fut_cols
        assert "created_at_utc" in fut_cols
        assert "updated_at_utc" in fut_cols
    finally:
        conn.close()


def test_legacy_orders_table_rows_are_preserved(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_orders_preserved.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                exchange_order_id TEXT,
                order_link_id TEXT UNIQUE,
                price TEXT,
                qty TEXT,
                status TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO orders (symbol, side, order_link_id, price, qty, status, created_at_utc)
            VALUES ('BTCUSDT', 'Buy', 'legacy-1', '50000', '0.001', 'Filled', '2026-03-09T00:00:00Z')
            """
        )
        conn.commit()
    finally:
        conn.close()

    conn2 = get_connection(db_path)
    try:
        row = conn2.execute("SELECT COUNT(*) FROM orders").fetchone()
        assert row is not None
        assert int(row[0]) == 1
        cols = _table_columns(conn2, "orders")
        assert "entry_price" in cols
        assert "exit_price" in cols
        assert "spot_holdings" in _table_names(conn2)
        assert "futures_positions" in _table_names(conn2)
    finally:
        conn2.close()
