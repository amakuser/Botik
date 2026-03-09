"""
Spot domain storage: balances, holdings, orders, fills and decisions.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


SPOT_HOLD_REASONS = {
    "strategy_entry",
    "manual_import",
    "unknown_recovered_from_exchange",
    "dust",
    "rebalance_hold",
    "stale_hold",
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


def _normalize_hold_reason(value: str) -> str:
    reason = str(value or "").strip()
    if reason not in SPOT_HOLD_REASONS:
        raise ValueError(f"Unsupported hold_reason={reason!r}")
    return reason


def ensure_spot_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS spot_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            asset TEXT NOT NULL,
            free_qty REAL NOT NULL DEFAULT 0.0,
            locked_qty REAL NOT NULL DEFAULT 0.0,
            total_qty REAL NOT NULL DEFAULT 0.0,
            source_of_truth TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(account_type, asset)
        );
        CREATE INDEX IF NOT EXISTS idx_spot_balances_account ON spot_balances(account_type, asset);

        CREATE TABLE IF NOT EXISTS spot_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            base_asset TEXT NOT NULL,
            free_qty REAL NOT NULL DEFAULT 0.0,
            locked_qty REAL NOT NULL DEFAULT 0.0,
            avg_entry_price REAL,
            hold_reason TEXT NOT NULL,
            source_of_truth TEXT NOT NULL,
            recovered_from_exchange INTEGER NOT NULL DEFAULT 0,
            strategy_owner TEXT,
            auto_sell_allowed INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(account_type, symbol, base_asset)
        );
        CREATE INDEX IF NOT EXISTS idx_spot_holdings_symbol ON spot_holdings(symbol, updated_at_utc);
        CREATE INDEX IF NOT EXISTS idx_spot_holdings_recovered ON spot_holdings(recovered_from_exchange, hold_reason);

        CREATE TABLE IF NOT EXISTS spot_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            order_type TEXT,
            time_in_force TEXT,
            price REAL,
            qty REAL,
            filled_qty REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL,
            strategy_owner TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(order_link_id)
        );
        CREATE INDEX IF NOT EXISTS idx_spot_orders_symbol_status ON spot_orders(symbol, status, updated_at_utc);
        CREATE INDEX IF NOT EXISTS idx_spot_orders_order_id ON spot_orders(order_id);

        CREATE TABLE IF NOT EXISTS spot_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            exec_id TEXT UNIQUE NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            price REAL NOT NULL,
            qty REAL NOT NULL,
            fee REAL,
            fee_currency TEXT,
            is_maker INTEGER,
            exec_time_ms INTEGER,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_fills_symbol_time ON spot_fills(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS spot_position_intents (
            intent_id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            intended_qty REAL NOT NULL,
            intended_price REAL,
            strategy_owner TEXT,
            profile_id TEXT,
            signal_id TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_intents_symbol ON spot_position_intents(symbol, created_at_utc);

        CREATE TABLE IF NOT EXISTS spot_exit_decisions (
            decision_id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            policy_name TEXT,
            pnl_pct REAL,
            pnl_quote REAL,
            payload_json TEXT,
            applied INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_exit_decisions_symbol ON spot_exit_decisions(symbol, created_at_utc);
        """
    )
    conn.commit()


def upsert_spot_balance(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    asset: str,
    free_qty: float,
    locked_qty: float,
    source_of_truth: str,
    updated_at_utc: str | None = None,
) -> None:
    updated = str(updated_at_utc or utc_now_iso())
    total_qty = max(_safe_float(free_qty), 0.0) + max(_safe_float(locked_qty), 0.0)
    conn.execute(
        """
        INSERT INTO spot_balances (
            account_type, asset, free_qty, locked_qty, total_qty, source_of_truth, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_type, asset) DO UPDATE SET
            free_qty=excluded.free_qty,
            locked_qty=excluded.locked_qty,
            total_qty=excluded.total_qty,
            source_of_truth=excluded.source_of_truth,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            str(account_type),
            str(asset).upper(),
            max(_safe_float(free_qty), 0.0),
            max(_safe_float(locked_qty), 0.0),
            total_qty,
            str(source_of_truth),
            updated,
            updated,
        ),
    )
    conn.commit()


def upsert_spot_holding(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    base_asset: str,
    free_qty: float,
    locked_qty: float,
    hold_reason: str,
    source_of_truth: str,
    recovered_from_exchange: bool,
    strategy_owner: str | None = None,
    avg_entry_price: float | None = None,
    auto_sell_allowed: bool = False,
    updated_at_utc: str | None = None,
) -> None:
    hold_reason_norm = _normalize_hold_reason(hold_reason)
    updated = str(updated_at_utc or utc_now_iso())
    conn.execute(
        """
        INSERT INTO spot_holdings (
            account_type,
            symbol,
            base_asset,
            free_qty,
            locked_qty,
            avg_entry_price,
            hold_reason,
            source_of_truth,
            recovered_from_exchange,
            strategy_owner,
            auto_sell_allowed,
            created_at_utc,
            updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_type, symbol, base_asset) DO UPDATE SET
            free_qty=excluded.free_qty,
            locked_qty=excluded.locked_qty,
            avg_entry_price=COALESCE(excluded.avg_entry_price, spot_holdings.avg_entry_price),
            hold_reason=excluded.hold_reason,
            source_of_truth=excluded.source_of_truth,
            recovered_from_exchange=excluded.recovered_from_exchange,
            strategy_owner=COALESCE(excluded.strategy_owner, spot_holdings.strategy_owner),
            auto_sell_allowed=excluded.auto_sell_allowed,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            str(account_type),
            str(symbol).upper(),
            str(base_asset).upper(),
            max(_safe_float(free_qty), 0.0),
            max(_safe_float(locked_qty), 0.0),
            (_safe_float(avg_entry_price) if avg_entry_price is not None else None),
            hold_reason_norm,
            str(source_of_truth),
            1 if recovered_from_exchange else 0,
            (str(strategy_owner) if strategy_owner else None),
            1 if auto_sell_allowed else 0,
            updated,
            updated,
        ),
    )
    conn.commit()


def list_spot_holdings(conn: sqlite3.Connection, *, account_type: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if account_type:
        where = "WHERE account_type=?"
        params.append(str(account_type))
    rows = conn.execute(
        f"""
        SELECT
            account_type, symbol, base_asset, free_qty, locked_qty, avg_entry_price,
            hold_reason, source_of_truth, recovered_from_exchange, strategy_owner,
            auto_sell_allowed, created_at_utc, updated_at_utc
        FROM spot_holdings
        {where}
        ORDER BY symbol ASC
        """,
        tuple(params),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "account_type": row[0],
                "symbol": row[1],
                "base_asset": row[2],
                "free_qty": _safe_float(row[3]),
                "locked_qty": _safe_float(row[4]),
                "avg_entry_price": (_safe_float(row[5]) if row[5] is not None else None),
                "hold_reason": row[6],
                "source_of_truth": row[7],
                "recovered_from_exchange": bool(int(row[8] or 0)),
                "strategy_owner": row[9],
                "auto_sell_allowed": bool(int(row[10] or 0)),
                "created_at_utc": row[11],
                "updated_at_utc": row[12],
            }
        )
    return out


def upsert_spot_order(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    side: str,
    status: str,
    price: float,
    qty: float,
    order_link_id: str | None = None,
    order_id: str | None = None,
    order_type: str | None = None,
    time_in_force: str | None = None,
    filled_qty: float = 0.0,
    strategy_owner: str | None = None,
    updated_at_utc: str | None = None,
) -> None:
    updated = str(updated_at_utc or utc_now_iso())
    link_id = str(order_link_id or f"spot-local-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO spot_orders (
            account_type, symbol, side, order_id, order_link_id, order_type, time_in_force,
            price, qty, filled_qty, status, strategy_owner, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_link_id) DO UPDATE SET
            order_id=COALESCE(excluded.order_id, spot_orders.order_id),
            status=excluded.status,
            price=excluded.price,
            qty=excluded.qty,
            filled_qty=excluded.filled_qty,
            order_type=COALESCE(excluded.order_type, spot_orders.order_type),
            time_in_force=COALESCE(excluded.time_in_force, spot_orders.time_in_force),
            strategy_owner=COALESCE(excluded.strategy_owner, spot_orders.strategy_owner),
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            str(account_type),
            str(symbol).upper(),
            str(side),
            order_id,
            link_id,
            order_type,
            time_in_force,
            _safe_float(price),
            max(_safe_float(qty), 0.0),
            max(_safe_float(filled_qty), 0.0),
            str(status),
            strategy_owner,
            updated,
            updated,
        ),
    )
    conn.commit()


def insert_spot_fill(
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
    fee: float | None = None,
    fee_currency: str | None = None,
    is_maker: bool | None = None,
    exec_time_ms: int | None = None,
    created_at_utc: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO spot_fills (
            account_type, symbol, side, exec_id, order_id, order_link_id, price, qty, fee, fee_currency,
            is_maker, exec_time_ms, created_at_utc
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
            (_safe_float(fee) if fee is not None else None),
            fee_currency,
            (1 if is_maker else 0 if is_maker is not None else None),
            exec_time_ms,
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()


def insert_spot_position_intent(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    side: str,
    intended_qty: float,
    intended_price: float | None = None,
    strategy_owner: str | None = None,
    profile_id: str | None = None,
    signal_id: str | None = None,
    status: str = "new",
    intent_id: str | None = None,
    created_at_utc: str | None = None,
) -> str:
    row_id = str(intent_id or f"sp-intent-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO spot_position_intents (
            intent_id, account_type, symbol, side, intended_qty, intended_price, strategy_owner,
            profile_id, signal_id, status, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            str(account_type),
            str(symbol).upper(),
            str(side),
            max(_safe_float(intended_qty), 0.0),
            (_safe_float(intended_price) if intended_price is not None else None),
            strategy_owner,
            profile_id,
            signal_id,
            str(status),
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()
    return row_id


def insert_spot_exit_decision(
    conn: sqlite3.Connection,
    *,
    account_type: str,
    symbol: str,
    decision_type: str,
    reason: str,
    policy_name: str | None = None,
    pnl_pct: float | None = None,
    pnl_quote: float | None = None,
    payload_json: str | None = None,
    applied: bool = False,
    decision_id: str | None = None,
    created_at_utc: str | None = None,
) -> str:
    row_id = str(decision_id or f"sp-exit-{uuid.uuid4().hex[:16]}")
    conn.execute(
        """
        INSERT INTO spot_exit_decisions (
            decision_id, account_type, symbol, decision_type, reason, policy_name, pnl_pct, pnl_quote,
            payload_json, applied, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            str(account_type),
            str(symbol).upper(),
            str(decision_type),
            str(reason),
            policy_name,
            (_safe_float(pnl_pct) if pnl_pct is not None else None),
            (_safe_float(pnl_quote) if pnl_quote is not None else None),
            payload_json,
            1 if applied else 0,
            str(created_at_utc or utc_now_iso()),
        ),
    )
    conn.commit()
    return row_id
