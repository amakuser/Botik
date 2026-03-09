"""
Futures domain storage: positions, open orders, fills and protection lifecycle.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


FUTURES_PROTECTION_STATUSES = {
    "unknown",
    "pending",
    "protected",
    "unprotected",
    "repairing",
    "closed",
    "failed",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize_protection_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in FUTURES_PROTECTION_STATUSES:
        raise ValueError(f"Unsupported protection_status={status!r}")
    return status


def ensure_futures_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS futures_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            position_idx INTEGER NOT NULL DEFAULT 0,
            margin_mode TEXT,
            leverage REAL,
            qty REAL NOT NULL DEFAULT 0.0,
            entry_price REAL,
            mark_price REAL,
            liq_price REAL,
            unrealized_pnl REAL,
            realized_pnl REAL,
            take_profit REAL,
            stop_loss REAL,
            trailing_stop REAL,
            protection_status TEXT NOT NULL,
            source_of_truth TEXT NOT NULL DEFAULT 'exchange',
            recovered_from_exchange INTEGER NOT NULL DEFAULT 0,
            strategy_owner TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(account_type, symbol, side, position_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_futures_positions_symbol ON futures_positions(symbol, updated_at_utc);
        CREATE INDEX IF NOT EXISTS idx_futures_positions_protection ON futures_positions(protection_status, updated_at_utc);

        CREATE TABLE IF NOT EXISTS futures_open_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            order_id TEXT,
            order_link_id TEXT,
            order_type TEXT,
            time_in_force TEXT,
            price REAL,
            qty REAL,
            status TEXT NOT NULL,
            reduce_only INTEGER,
            close_on_trigger INTEGER,
            strategy_owner TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(order_link_id)
        );
        CREATE INDEX IF NOT EXISTS idx_futures_orders_symbol_status ON futures_open_orders(symbol, status, updated_at_utc);
        CREATE INDEX IF NOT EXISTS idx_futures_orders_order_id ON futures_open_orders(order_id);

        CREATE TABLE IF NOT EXISTS futures_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            exec_id TEXT UNIQUE NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            price REAL NOT NULL,
            qty REAL NOT NULL,
            exec_fee REAL,
            fee_currency TEXT,
            is_maker INTEGER,
            exec_time_ms INTEGER,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_futures_fills_symbol_time ON futures_fills(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS futures_protection_orders (
            protection_id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            position_idx INTEGER NOT NULL DEFAULT 0,
            stop_loss REAL,
            take_profit REAL,
            trailing_stop REAL,
            status TEXT NOT NULL,
            source_of_truth TEXT NOT NULL,
            sl_order_id TEXT,
            tp_order_id TEXT,
            trailing_order_id TEXT,
            details_json TEXT,
            last_sync_at_utc TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(account_type, symbol, side, position_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_futures_protection_status ON futures_protection_orders(status, updated_at_utc);

        CREATE TABLE IF NOT EXISTS futures_funding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            position_idx INTEGER,
            funding_rate REAL,
            funding_fee REAL,
            funding_time_ms INTEGER,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_futures_funding_symbol_time ON futures_funding_events(symbol, funding_time_ms);

        CREATE TABLE IF NOT EXISTS futures_liquidation_risk_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            position_idx INTEGER,
            mark_price REAL,
            liq_price REAL,
            distance_to_liq_bps REAL,
            margin_ratio REAL,
            payload_json TEXT,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_futures_liq_snapshots_symbol_time
            ON futures_liquidation_risk_snapshots(symbol, created_at_utc);

        CREATE TABLE IF NOT EXISTS futures_position_decisions (
            decision_id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            position_idx INTEGER,
            decision_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            policy_name TEXT,
            payload_json TEXT,
            applied INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_futures_decisions_symbol ON futures_position_decisions(symbol, created_at_utc);
        """
    )
    conn.commit()


def upsert_futures_position(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    side: str,
    position_idx: int,
    margin_mode: str | None,
    leverage: float | None,
    qty: float,
    entry_price: float | None,
    mark_price: float | None,
    liq_price: float | None,
    unrealized_pnl: float | None,
    realized_pnl: float | None,
    take_profit: float | None,
    stop_loss: float | None,
    trailing_stop: float | None,
    protection_status: str,
    strategy_owner: str | None,
    source_of_truth: str,
    recovered_from_exchange: bool,
    updated_at_utc: str | None = None,
) -> None:
    status = _normalize_protection_status(protection_status)
    updated = str(updated_at_utc or utc_now_iso())
    conn.execute(
        """
        INSERT INTO futures_positions (
            account_type, symbol, side, position_idx, margin_mode, leverage, qty, entry_price, mark_price, liq_price,
            unrealized_pnl, realized_pnl, take_profit, stop_loss, trailing_stop, protection_status, source_of_truth,
            recovered_from_exchange, strategy_owner, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_type, symbol, side, position_idx) DO UPDATE SET
            margin_mode=excluded.margin_mode,
            leverage=excluded.leverage,
            qty=excluded.qty,
            entry_price=excluded.entry_price,
            mark_price=excluded.mark_price,
            liq_price=excluded.liq_price,
            unrealized_pnl=excluded.unrealized_pnl,
            realized_pnl=excluded.realized_pnl,
            take_profit=excluded.take_profit,
            stop_loss=excluded.stop_loss,
            trailing_stop=excluded.trailing_stop,
            protection_status=excluded.protection_status,
            source_of_truth=excluded.source_of_truth,
            recovered_from_exchange=excluded.recovered_from_exchange,
            strategy_owner=COALESCE(excluded.strategy_owner, futures_positions.strategy_owner),
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            str(account_type),
            str(symbol).upper(),
            str(side),
            _safe_int(position_idx),
            margin_mode,
            (_safe_float(leverage) if leverage is not None else None),
            _safe_float(qty),
            (_safe_float(entry_price) if entry_price is not None else None),
            (_safe_float(mark_price) if mark_price is not None else None),
            (_safe_float(liq_price) if liq_price is not None else None),
            (_safe_float(unrealized_pnl) if unrealized_pnl is not None else None),
            (_safe_float(realized_pnl) if realized_pnl is not None else None),
            (_safe_float(take_profit) if take_profit is not None else None),
            (_safe_float(stop_loss) if stop_loss is not None else None),
            (_safe_float(trailing_stop) if trailing_stop is not None else None),
            status,
            str(source_of_truth),
            1 if recovered_from_exchange else 0,
            strategy_owner,
            updated,
            updated,
        ),
    )
    conn.commit()


def list_futures_positions(conn: sqlite3.Connection, *, account_type: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if account_type:
        where = "WHERE account_type=?"
        params.append(str(account_type))
    rows = conn.execute(
        f"""
        SELECT
            account_type, symbol, side, position_idx, margin_mode, leverage, qty, entry_price, mark_price, liq_price,
            unrealized_pnl, realized_pnl, take_profit, stop_loss, trailing_stop, protection_status, source_of_truth,
            recovered_from_exchange, strategy_owner, created_at_utc, updated_at_utc
        FROM futures_positions
        {where}
        ORDER BY symbol ASC, side ASC, position_idx ASC
        """,
        tuple(params),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "account_type": row[0],
                "symbol": row[1],
                "side": row[2],
                "position_idx": _safe_int(row[3]),
                "margin_mode": row[4],
                "leverage": (_safe_float(row[5]) if row[5] is not None else None),
                "qty": _safe_float(row[6]),
                "entry_price": (_safe_float(row[7]) if row[7] is not None else None),
                "mark_price": (_safe_float(row[8]) if row[8] is not None else None),
                "liq_price": (_safe_float(row[9]) if row[9] is not None else None),
                "unrealized_pnl": (_safe_float(row[10]) if row[10] is not None else None),
                "realized_pnl": (_safe_float(row[11]) if row[11] is not None else None),
                "take_profit": (_safe_float(row[12]) if row[12] is not None else None),
                "stop_loss": (_safe_float(row[13]) if row[13] is not None else None),
                "trailing_stop": (_safe_float(row[14]) if row[14] is not None else None),
                "protection_status": str(row[15]),
                "source_of_truth": row[16],
                "recovered_from_exchange": bool(int(row[17] or 0)),
                "strategy_owner": row[18],
                "created_at_utc": row[19],
                "updated_at_utc": row[20],
            }
        )
    return out


def upsert_futures_open_order(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    status: str,
    order_link_id: str | None = None,
    order_id: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    time_in_force: str | None = None,
    price: float | None = None,
    qty: float | None = None,
    reduce_only: bool | None = None,
    close_on_trigger: bool | None = None,
    strategy_owner: str | None = None,
    updated_at_utc: str | None = None,
) -> str:
    updated = str(updated_at_utc or utc_now_iso())
    link_id = str(order_link_id or f"fut-local-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO futures_open_orders (
            account_type, symbol, side, order_id, order_link_id, order_type, time_in_force, price, qty, status,
            reduce_only, close_on_trigger, strategy_owner, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_link_id) DO UPDATE SET
            order_id=COALESCE(excluded.order_id, futures_open_orders.order_id),
            status=excluded.status,
            side=COALESCE(excluded.side, futures_open_orders.side),
            order_type=COALESCE(excluded.order_type, futures_open_orders.order_type),
            time_in_force=COALESCE(excluded.time_in_force, futures_open_orders.time_in_force),
            price=COALESCE(excluded.price, futures_open_orders.price),
            qty=COALESCE(excluded.qty, futures_open_orders.qty),
            reduce_only=COALESCE(excluded.reduce_only, futures_open_orders.reduce_only),
            close_on_trigger=COALESCE(excluded.close_on_trigger, futures_open_orders.close_on_trigger),
            strategy_owner=COALESCE(excluded.strategy_owner, futures_open_orders.strategy_owner),
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            str(account_type),
            str(symbol).upper(),
            side,
            order_id,
            link_id,
            order_type,
            time_in_force,
            (_safe_float(price) if price is not None else None),
            (_safe_float(qty) if qty is not None else None),
            str(status),
            (1 if reduce_only else 0 if reduce_only is not None else None),
            (1 if close_on_trigger else 0 if close_on_trigger is not None else None),
            strategy_owner,
            updated,
            updated,
        ),
    )
    conn.commit()
    return link_id


def insert_futures_fill(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    side: str,
    exec_id: str,
    price: float,
    qty: float,
    order_id: str | None = None,
    order_link_id: str | None = None,
    exec_fee: float | None = None,
    fee_currency: str | None = None,
    is_maker: bool | None = None,
    exec_time_ms: int | None = None,
    created_at_utc: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO futures_fills (
            account_type, symbol, side, exec_id, order_id, order_link_id, price, qty,
            exec_fee, fee_currency, is_maker, exec_time_ms, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exec_id) DO NOTHING
        """,
        (
            str(account_type),
            str(symbol).upper(),
            str(side),
            str(exec_id),
            order_id,
            order_link_id,
            _safe_float(price),
            max(_safe_float(qty), 0.0),
            (_safe_float(exec_fee) if exec_fee is not None else None),
            fee_currency,
            (1 if is_maker else 0 if is_maker is not None else None),
            exec_time_ms,
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()


def upsert_futures_protection(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    side: str,
    position_idx: int,
    status: str,
    source_of_truth: str,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trailing_stop: float | None = None,
    sl_order_id: str | None = None,
    tp_order_id: str | None = None,
    trailing_order_id: str | None = None,
    details: dict[str, Any] | str | None = None,
    updated_at_utc: str | None = None,
    protection_id: str | None = None,
) -> str:
    status_norm = _normalize_protection_status(status)
    updated = str(updated_at_utc or utc_now_iso())
    prot_id = str(protection_id or f"fut-prot-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO futures_protection_orders (
            protection_id, account_type, symbol, side, position_idx, stop_loss, take_profit, trailing_stop, status,
            source_of_truth, sl_order_id, tp_order_id, trailing_order_id, details_json, last_sync_at_utc,
            created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_type, symbol, side, position_idx) DO UPDATE SET
            status=excluded.status,
            stop_loss=excluded.stop_loss,
            take_profit=excluded.take_profit,
            trailing_stop=excluded.trailing_stop,
            source_of_truth=excluded.source_of_truth,
            sl_order_id=COALESCE(excluded.sl_order_id, futures_protection_orders.sl_order_id),
            tp_order_id=COALESCE(excluded.tp_order_id, futures_protection_orders.tp_order_id),
            trailing_order_id=COALESCE(excluded.trailing_order_id, futures_protection_orders.trailing_order_id),
            details_json=excluded.details_json,
            last_sync_at_utc=excluded.last_sync_at_utc,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            prot_id,
            str(account_type),
            str(symbol).upper(),
            str(side),
            _safe_int(position_idx),
            (_safe_float(stop_loss) if stop_loss is not None else None),
            (_safe_float(take_profit) if take_profit is not None else None),
            (_safe_float(trailing_stop) if trailing_stop is not None else None),
            status_norm,
            str(source_of_truth),
            sl_order_id,
            tp_order_id,
            trailing_order_id,
            _json_text(details or {}),
            updated,
            updated,
            updated,
        ),
    )
    conn.commit()
    return prot_id


def list_unprotected_futures_symbols(conn: sqlite3.Connection, *, account_type: str | None = None) -> list[str]:
    params: list[Any] = []
    where = "WHERE LOWER(protection_status)='unprotected' AND ABS(COALESCE(qty, 0)) > 0"
    if account_type:
        where += " AND account_type=?"
        params.append(str(account_type))
    rows = conn.execute(
        f"SELECT DISTINCT symbol FROM futures_positions {where} ORDER BY symbol ASC",
        tuple(params),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def insert_futures_position_decision(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    decision_type: str,
    reason: str,
    side: str | None = None,
    position_idx: int | None = None,
    policy_name: str | None = None,
    payload: dict[str, Any] | str | None = None,
    applied: bool = False,
    decision_id: str | None = None,
    created_at_utc: str | None = None,
) -> str:
    row_id = str(decision_id or f"fut-dec-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO futures_position_decisions (
            decision_id, account_type, symbol, side, position_idx, decision_type, reason, policy_name,
            payload_json, applied, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            str(account_type),
            str(symbol).upper(),
            side,
            (_safe_int(position_idx) if position_idx is not None else None),
            str(decision_type),
            str(reason),
            policy_name,
            _json_text(payload or {}),
            1 if applied else 0,
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()
    return row_id
