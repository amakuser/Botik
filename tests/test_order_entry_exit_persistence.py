from __future__ import annotations

import sqlite3
from pathlib import Path

from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, set_order_signal_map
from src.botik.storage.sqlite_store import (
    get_connection,
    insert_order,
    update_orders_entry_exit_for_signal,
)


def _orders_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(r[1]) for r in conn.execute("PRAGMA table_info(orders)").fetchall()}


def test_orders_schema_migrates_entry_exit_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_orders.db"
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
        conn.commit()
    finally:
        conn.close()

    conn2 = get_connection(db_path)
    try:
        cols = _orders_columns(conn2)
        assert "entry_price" in cols
        assert "exit_price" in cols
    finally:
        conn2.close()


def test_update_orders_entry_exit_for_signal(tmp_path: Path) -> None:
    db_path = tmp_path / "orders_signal_map.db"
    conn = get_connection(db_path)
    try:
        ensure_lifecycle_schema(conn)
        insert_order(
            conn,
            symbol="BTCUSDT",
            side="Buy",
            order_link_id="ol-entry-1",
            price="60000",
            qty="0.001",
            status="Filled",
            created_at_utc="2026-03-08T12:00:00Z",
        )
        set_order_signal_map(conn, "ol-entry-1", "sig-1")

        update_orders_entry_exit_for_signal(
            conn,
            signal_id="sig-1",
            entry_price=60000.25,
            exit_price=60020.75,
            updated_at_utc="2026-03-08T12:01:00Z",
        )

        row = conn.execute(
            "SELECT entry_price, exit_price, updated_at_utc FROM orders WHERE order_link_id=?",
            ("ol-entry-1",),
        ).fetchone()
        assert row is not None
        assert abs(float(row[0]) - 60000.25) < 1e-9
        assert abs(float(row[1]) - 60020.75) < 1e-9
        assert str(row[2]) == "2026-03-08T12:01:00Z"
    finally:
        conn.close()
