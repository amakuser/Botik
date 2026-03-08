"""
SQLite-хранилище: WAL, таблицы orders, fills, metrics, pnl_snapshots, model_registry.
Сырой стакан на диск не пишем — только агрегаты и ордера/сделки (архив улик).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Включение WAL и создание таблиц при первом подключении


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    cols = _table_columns(conn, table)
    if name in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
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
        );
        CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at_utc);

        CREATE TABLE IF NOT EXISTS fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_link_id TEXT,
            exchange_order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price TEXT NOT NULL,
            qty TEXT NOT NULL,
            fee TEXT,
            fee_currency TEXT,
            liquidity TEXT,
            filled_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol);
        CREATE INDEX IF NOT EXISTS idx_fills_filled_at ON fills(filled_at_utc);

        CREATE TABLE IF NOT EXISTS metrics_1s (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            best_bid REAL,
            best_ask REAL,
            mid REAL,
            spread_ticks INTEGER,
            imbalance_top_n REAL
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_symbol_ts ON metrics_1s(symbol, ts_utc);

        CREATE TABLE IF NOT EXISTS pnl_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            realised_pnl_usdt REAL,
            total_fees_usdt REAL,
            extra_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pnl_ts ON pnl_snapshots(ts_utc);

        CREATE TABLE IF NOT EXISTS model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT UNIQUE NOT NULL,
            path_or_payload TEXT,
            metrics_json TEXT,
            created_at_utc TEXT NOT NULL,
            is_active INTEGER DEFAULT 0
        );
    """)
    _ensure_column(conn, "orders", "entry_price", "REAL")
    _ensure_column(conn, "orders", "exit_price", "REAL")
    conn.commit()


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Возвращает подключение с включённым WAL и созданными таблицами."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _ensure_schema(conn)
    return conn


def insert_order(
    conn: sqlite3.Connection,
    symbol: str,
    side: str,
    order_link_id: str,
    price: str,
    qty: str,
    status: str,
    created_at_utc: str,
    exchange_order_id: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO orders (symbol, side, exchange_order_id, order_link_id, price, qty, status, created_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, side, exchange_order_id, order_link_id, price, qty, status, created_at_utc),
    )
    conn.commit()
    return cur.lastrowid or 0


def update_order_status(
    conn: sqlite3.Connection,
    order_link_id: str,
    status: str,
    updated_at_utc: str,
    exchange_order_id: str | None = None,
) -> None:
    if exchange_order_id:
        conn.execute(
            "UPDATE orders SET status=?, updated_at_utc=?, exchange_order_id=? WHERE order_link_id=?",
            (status, updated_at_utc, exchange_order_id, order_link_id),
        )
    else:
        conn.execute(
            "UPDATE orders SET status=?, updated_at_utc=? WHERE order_link_id=?",
            (status, updated_at_utc, order_link_id),
        )
    conn.commit()


def update_orders_entry_exit_for_signal(
    conn: sqlite3.Connection,
    *,
    signal_id: str,
    entry_price: float | None,
    exit_price: float | None,
    updated_at_utc: str,
) -> None:
    if not signal_id:
        return
    if not _table_exists(conn, "order_signal_map"):
        return
    conn.execute(
        """
        UPDATE orders
        SET entry_price = ?, exit_price = ?, updated_at_utc = ?
        WHERE order_link_id IN (
            SELECT order_link_id
            FROM order_signal_map
            WHERE signal_id = ?
        )
        """,
        (entry_price, exit_price, updated_at_utc, signal_id),
    )
    conn.commit()


def insert_fill(
    conn: sqlite3.Connection,
    symbol: str,
    side: str,
    price: str,
    qty: str,
    filled_at_utc: str,
    order_link_id: str | None = None,
    exchange_order_id: str | None = None,
    fee: str | None = None,
    fee_currency: str | None = None,
    liquidity: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO fills (order_link_id, exchange_order_id, symbol, side, price, qty, fee, fee_currency, liquidity, filled_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (order_link_id, exchange_order_id, symbol, side, price, qty, fee, fee_currency, liquidity, filled_at_utc),
    )
    conn.commit()
    return cur.lastrowid or 0


def insert_metrics(
    conn: sqlite3.Connection,
    symbol: str,
    ts_utc: str,
    best_bid: float | None = None,
    best_ask: float | None = None,
    mid: float | None = None,
    spread_ticks: int | None = None,
    imbalance_top_n: float | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO metrics_1s (symbol, ts_utc, best_bid, best_ask, mid, spread_ticks, imbalance_top_n)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, ts_utc, best_bid, best_ask, mid, spread_ticks, imbalance_top_n),
    )
    conn.commit()
    return cur.lastrowid or 0


def insert_pnl_snapshot(
    conn: sqlite3.Connection,
    ts_utc: str,
    realised_pnl_usdt: float | None = None,
    total_fees_usdt: float | None = None,
    extra_json: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO pnl_snapshots (ts_utc, realised_pnl_usdt, total_fees_usdt, extra_json) VALUES (?, ?, ?, ?)",
        (ts_utc, realised_pnl_usdt, total_fees_usdt, extra_json),
    )
    conn.commit()
    return cur.lastrowid or 0


def upsert_model_registry(
    conn: sqlite3.Connection,
    model_id: str,
    path_or_payload: str,
    metrics_json: str,
    created_at_utc: str,
    is_active: bool = False,
) -> None:
    if is_active:
        conn.execute("UPDATE model_registry SET is_active=0")
    conn.execute(
        """INSERT INTO model_registry (model_id, path_or_payload, metrics_json, created_at_utc, is_active)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(model_id) DO UPDATE SET
             path_or_payload=excluded.path_or_payload,
             metrics_json=excluded.metrics_json,
             created_at_utc=excluded.created_at_utc,
             is_active=excluded.is_active""",
        (model_id, path_or_payload, metrics_json, created_at_utc, 1 if is_active else 0),
    )
    conn.commit()


def get_active_model(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT model_id, path_or_payload, metrics_json FROM model_registry WHERE is_active=1 LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"model_id": row[0], "path_or_payload": row[1], "metrics_json": row[2]}


# --- Как проверить: get_connection("data/test.db"), insert_metrics(conn, "BTCUSDT", "2025-01-01T00:00:00Z", mid=50000.0), затем SELECT.
# --- Частые ошибки: не вызывать conn.commit() после вставки; держать соединение открытым между циклами (но не забывать закрывать при выходе).
# --- Что улучшить позже: контекстный менеджер Store(conn); батчевые вставки metrics.
