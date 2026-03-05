"""
Lifecycle storage for strategy signals, order events, executions and outcomes.

This module is additive and does not replace existing sqlite_store tables.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_lifecycle_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            ts_signal_ms INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            best_bid REAL,
            best_ask REAL,
            mid REAL,
            spread_bps REAL,
            depth_bid_quote REAL,
            depth_ask_quote REAL,
            slippage_buy_bps_est REAL,
            slippage_sell_bps_est REAL,
            trades_per_min REAL,
            p95_trade_gap_ms REAL,
            vol_1s_bps REAL,
            min_required_spread_bps REAL,
            scanner_status TEXT,
            model_version TEXT,
            order_size_quote REAL,
            order_size_base REAL,
            entry_price REAL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts ON signals(symbol, ts_signal_ms);

        CREATE TABLE IF NOT EXISTS order_signal_map (
            order_link_id TEXT PRIMARY KEY,
            signal_id TEXT,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_order_signal_signal ON order_signal_map(signal_id);

        CREATE TABLE IF NOT EXISTS order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            order_link_id TEXT,
            signal_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT,
            order_type TEXT,
            time_in_force TEXT,
            price REAL,
            qty REAL,
            order_status TEXT,
            avg_price REAL,
            cum_exec_qty REAL,
            cum_exec_value REAL,
            created_time_ms INTEGER,
            updated_time_ms INTEGER,
            event_time_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_order_events_order_link ON order_events(order_link_id);
        CREATE INDEX IF NOT EXISTS idx_order_events_signal ON order_events(signal_id);
        CREATE INDEX IF NOT EXISTS idx_order_events_symbol_ts ON order_events(symbol, event_time_utc);

        CREATE TABLE IF NOT EXISTS executions_raw (
            exec_id TEXT PRIMARY KEY,
            order_id TEXT,
            order_link_id TEXT,
            signal_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT,
            order_type TEXT,
            exec_price REAL NOT NULL,
            exec_qty REAL NOT NULL,
            exec_fee REAL,
            fee_rate REAL,
            fee_currency TEXT,
            is_maker INTEGER,
            exec_time_ms INTEGER,
            recorded_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_exec_signal ON executions_raw(signal_id);
        CREATE INDEX IF NOT EXISTS idx_exec_symbol_time ON executions_raw(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS outcomes (
            signal_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            entry_vwap REAL,
            exit_vwap REAL,
            filled_qty REAL,
            hold_time_ms INTEGER,
            gross_pnl_quote REAL,
            net_pnl_quote REAL,
            net_edge_bps REAL,
            max_adverse_excursion_bps REAL,
            max_favorable_excursion_bps REAL,
            was_fully_filled INTEGER,
            was_profitable INTEGER,
            exit_reason TEXT,
            closed_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outcomes_symbol_close ON outcomes(symbol, closed_at_utc);
        """
    )
    conn.commit()


def set_order_signal_map(conn: sqlite3.Connection, order_link_id: str, signal_id: str | None) -> None:
    conn.execute(
        """
        INSERT INTO order_signal_map (order_link_id, signal_id, created_at_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(order_link_id) DO UPDATE SET signal_id=excluded.signal_id
        """,
        (order_link_id, signal_id, _utc_now_iso()),
    )
    conn.commit()


def get_signal_id_for_order_link(conn: sqlite3.Connection, order_link_id: str | None) -> str | None:
    if not order_link_id:
        return None
    row = conn.execute(
        "SELECT signal_id FROM order_signal_map WHERE order_link_id = ? LIMIT 1",
        (order_link_id,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def insert_signal_snapshot(
    conn: sqlite3.Connection,
    signal_id: str,
    ts_signal_ms: int,
    symbol: str,
    side: str,
    best_bid: float,
    best_ask: float,
    mid: float,
    spread_bps: float,
    depth_bid_quote: float,
    depth_ask_quote: float,
    slippage_buy_bps_est: float,
    slippage_sell_bps_est: float,
    trades_per_min: float,
    p95_trade_gap_ms: float,
    vol_1s_bps: float,
    min_required_spread_bps: float,
    scanner_status: str,
    model_version: str,
    order_size_quote: float,
    order_size_base: float,
    entry_price: float,
) -> None:
    conn.execute(
        """
        INSERT INTO signals (
            signal_id, ts_signal_ms, symbol, side, best_bid, best_ask, mid, spread_bps,
            depth_bid_quote, depth_ask_quote, slippage_buy_bps_est, slippage_sell_bps_est,
            trades_per_min, p95_trade_gap_ms, vol_1s_bps, min_required_spread_bps,
            scanner_status, model_version, order_size_quote, order_size_base, entry_price, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(signal_id) DO NOTHING
        """,
        (
            signal_id,
            ts_signal_ms,
            symbol,
            side,
            best_bid,
            best_ask,
            mid,
            spread_bps,
            depth_bid_quote,
            depth_ask_quote,
            slippage_buy_bps_est,
            slippage_sell_bps_est,
            trades_per_min,
            p95_trade_gap_ms,
            vol_1s_bps,
            min_required_spread_bps,
            scanner_status,
            model_version,
            order_size_quote,
            order_size_base,
            entry_price,
            _utc_now_iso(),
        ),
    )
    conn.commit()


def insert_order_event(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    order_link_id: str | None = None,
    order_id: str | None = None,
    signal_id: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    time_in_force: str | None = None,
    price: float | None = None,
    qty: float | None = None,
    order_status: str | None = None,
    avg_price: float | None = None,
    cum_exec_qty: float | None = None,
    cum_exec_value: float | None = None,
    created_time_ms: int | None = None,
    updated_time_ms: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO order_events (
            order_id, order_link_id, signal_id, symbol, side, order_type, time_in_force, price, qty,
            order_status, avg_price, cum_exec_qty, cum_exec_value, created_time_ms, updated_time_ms, event_time_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            order_link_id,
            signal_id,
            symbol,
            side,
            order_type,
            time_in_force,
            price,
            qty,
            order_status,
            avg_price,
            cum_exec_qty,
            cum_exec_value,
            created_time_ms,
            updated_time_ms,
            _utc_now_iso(),
        ),
    )
    conn.commit()


def insert_execution_event(
    conn: sqlite3.Connection,
    *,
    exec_id: str,
    symbol: str,
    exec_price: float,
    exec_qty: float,
    order_id: str | None = None,
    order_link_id: str | None = None,
    signal_id: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    exec_fee: float | None = None,
    fee_rate: float | None = None,
    fee_currency: str | None = None,
    is_maker: bool | None = None,
    exec_time_ms: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO executions_raw (
            exec_id, order_id, order_link_id, signal_id, symbol, side, order_type,
            exec_price, exec_qty, exec_fee, fee_rate, fee_currency, is_maker, exec_time_ms, recorded_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exec_id) DO NOTHING
        """,
        (
            exec_id,
            order_id,
            order_link_id,
            signal_id,
            symbol,
            side,
            order_type,
            exec_price,
            exec_qty,
            exec_fee,
            fee_rate,
            fee_currency,
            1 if is_maker else 0 if is_maker is not None else None,
            exec_time_ms,
            _utc_now_iso(),
        ),
    )
    conn.commit()


def upsert_outcome(
    conn: sqlite3.Connection,
    *,
    signal_id: str,
    symbol: str,
    entry_vwap: float | None,
    exit_vwap: float | None,
    filled_qty: float | None,
    hold_time_ms: int | None,
    gross_pnl_quote: float | None,
    net_pnl_quote: float | None,
    net_edge_bps: float | None,
    max_adverse_excursion_bps: float | None,
    max_favorable_excursion_bps: float | None,
    was_fully_filled: bool,
    was_profitable: bool,
    exit_reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO outcomes (
            signal_id, symbol, entry_vwap, exit_vwap, filled_qty, hold_time_ms, gross_pnl_quote, net_pnl_quote,
            net_edge_bps, max_adverse_excursion_bps, max_favorable_excursion_bps, was_fully_filled, was_profitable,
            exit_reason, closed_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(signal_id) DO UPDATE SET
            symbol=excluded.symbol,
            entry_vwap=excluded.entry_vwap,
            exit_vwap=excluded.exit_vwap,
            filled_qty=excluded.filled_qty,
            hold_time_ms=excluded.hold_time_ms,
            gross_pnl_quote=excluded.gross_pnl_quote,
            net_pnl_quote=excluded.net_pnl_quote,
            net_edge_bps=excluded.net_edge_bps,
            max_adverse_excursion_bps=excluded.max_adverse_excursion_bps,
            max_favorable_excursion_bps=excluded.max_favorable_excursion_bps,
            was_fully_filled=excluded.was_fully_filled,
            was_profitable=excluded.was_profitable,
            exit_reason=excluded.exit_reason,
            closed_at_utc=excluded.closed_at_utc
        """,
        (
            signal_id,
            symbol,
            entry_vwap,
            exit_vwap,
            filled_qty,
            hold_time_ms,
            gross_pnl_quote,
            net_pnl_quote,
            net_edge_bps,
            max_adverse_excursion_bps,
            max_favorable_excursion_bps,
            1 if was_fully_filled else 0,
            1 if was_profitable else 0,
            exit_reason,
            _utc_now_iso(),
        ),
    )
    conn.commit()


def resolve_db_path(db_path: str | Path) -> Path:
    return Path(db_path)
