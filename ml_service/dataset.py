"""
Lifecycle dataset loader for ML service.

Source tables:
- signals
- executions_raw (aggregated per signal)
- outcomes
"""
from __future__ import annotations

import sqlite3
import zlib
from typing import Any

import numpy as np

from src.botik.storage.lifecycle_store import ensure_lifecycle_schema


FEATURE_NAMES: list[str] = [
    "spread_bps_at_signal",
    "depth_bid_quote_at_signal",
    "depth_ask_quote_at_signal",
    "slippage_buy_bps_est",
    "slippage_sell_bps_est",
    "trades_per_min_at_signal",
    "p95_trade_gap_ms_at_signal",
    "vol_1s_bps_at_signal",
    "min_required_spread_bps",
    "order_size_quote",
    "order_size_base",
    "action_entry_tick_offset",
    "action_order_qty_base",
    "action_target_profit",
    "action_safety_buffer",
    "action_min_top_book_qty",
    "action_stop_loss_pct",
    "action_take_profit_pct",
    "action_hold_timeout_sec",
    "action_maker_only",
    "side_sign",
    "symbol_hash",
    "profile_hash",
    "model_version_hash",
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_hash_to_unit(text: str) -> float:
    raw = zlib.adler32(text.encode("utf-8")) & 0xFFFFFFFF
    return float(raw % 100000) / 100000.0


def _row_to_features(row: sqlite3.Row) -> list[float]:
    side = str(row["side"] or "").strip().lower()
    side_sign = 1.0 if side == "buy" else -1.0 if side == "sell" else 0.0
    symbol_hash = _stable_hash_to_unit(str(row["symbol"] or ""))
    profile_hash = _stable_hash_to_unit(str(row["profile_id"] or ""))
    model_hash = _stable_hash_to_unit(str(row["model_version"] or ""))

    return [
        _to_float(row["spread_bps_at_signal"]),
        _to_float(row["depth_bid_quote_at_signal"]),
        _to_float(row["depth_ask_quote_at_signal"]),
        _to_float(row["slippage_buy_bps_est"]),
        _to_float(row["slippage_sell_bps_est"]),
        _to_float(row["trades_per_min_at_signal"]),
        _to_float(row["p95_trade_gap_ms_at_signal"]),
        _to_float(row["vol_1s_bps_at_signal"]),
        _to_float(row["min_required_spread_bps"]),
        _to_float(row["order_size_quote"]),
        _to_float(row["order_size_base"]),
        _to_float(row["action_entry_tick_offset"]),
        _to_float(row["action_order_qty_base"]),
        _to_float(row["action_target_profit"]),
        _to_float(row["action_safety_buffer"]),
        _to_float(row["action_min_top_book_qty"]),
        _to_float(row["action_stop_loss_pct"]),
        _to_float(row["action_take_profit_pct"]),
        _to_float(row["action_hold_timeout_sec"]),
        _to_float(row["action_maker_only"]),
        side_sign,
        symbol_hash,
        profile_hash,
        model_hash,
    ]


def _select_rows(
    conn: sqlite3.Connection,
    *,
    limit: int,
    closed_only: bool,
    symbol: str | None = None,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, "signals"):
        return []

    where: list[str] = []
    params: list[Any] = []
    if closed_only:
        where.append("o.signal_id IS NOT NULL")
    if symbol:
        where.append("s.symbol = ?")
        params.append(symbol)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    query = f"""
        WITH exec_agg AS (
            SELECT
                signal_id,
                MIN(exec_time_ms) AS first_exec_time_ms,
                SUM(exec_qty) AS total_exec_qty,
                SUM(exec_price * exec_qty) AS total_exec_quote,
                SUM(COALESCE(exec_fee, 0)) AS total_fees_quote
            FROM executions_raw
            WHERE signal_id IS NOT NULL AND signal_id <> ''
            GROUP BY signal_id
        )
        SELECT
            s.signal_id,
            s.ts_signal_ms,
            s.symbol,
            s.side,
            s.model_version,
            s.profile_id,
            s.action_entry_tick_offset,
            s.action_order_qty_base,
            s.action_target_profit,
            s.action_safety_buffer,
            s.action_min_top_book_qty,
            s.action_stop_loss_pct,
            s.action_take_profit_pct,
            s.action_hold_timeout_sec,
            s.action_maker_only,
            s.spread_bps AS spread_bps_at_signal,
            s.depth_bid_quote AS depth_bid_quote_at_signal,
            s.depth_ask_quote AS depth_ask_quote_at_signal,
            s.slippage_buy_bps_est,
            s.slippage_sell_bps_est,
            s.trades_per_min AS trades_per_min_at_signal,
            s.p95_trade_gap_ms AS p95_trade_gap_ms_at_signal,
            s.vol_1s_bps AS vol_1s_bps_at_signal,
            s.min_required_spread_bps,
            s.order_size_quote,
            s.order_size_base,
            s.entry_price AS entry_price_decision,
            COALESCE(e.first_exec_time_ms, 0) AS entry_fill_time_ms,
            COALESCE(e.total_exec_qty, 0) AS total_exec_qty,
            COALESCE(e.total_exec_quote, 0) AS total_exec_quote,
            COALESCE(e.total_fees_quote, 0) AS total_fees_quote,
            o.entry_vwap,
            o.exit_vwap,
            o.hold_time_ms,
            o.net_pnl_quote,
            o.net_edge_bps,
            o.exit_reason
        FROM signals s
        LEFT JOIN exec_agg e ON e.signal_id = s.signal_id
        LEFT JOIN outcomes o ON o.signal_id = s.signal_id
        {where_sql}
        ORDER BY s.ts_signal_ms ASC
        LIMIT ?
    """
    return conn.execute(query, params).fetchall()


def build_matrices_from_rows(
    rows: list[sqlite3.Row],
    *,
    target_edge_bps: float,
) -> dict[str, Any]:
    if not rows:
        empty = np.zeros((0, len(FEATURE_NAMES)), dtype=float)
        return {
            "rows": [],
            "X": empty,
            "y_open": np.zeros((0,), dtype=int),
            "y_fill": np.zeros((0,), dtype=int),
            "y_edge": np.zeros((0,), dtype=float),
        }

    X: list[list[float]] = []
    y_open: list[int] = []
    y_fill: list[int] = []
    y_edge: list[float] = []

    for row in rows:
        X.append(_row_to_features(row))
        net_edge = row["net_edge_bps"]
        y_open.append(1 if net_edge is not None and _to_float(net_edge) > float(target_edge_bps) else 0)
        total_exec_qty = _to_float(row["total_exec_qty"])
        y_fill.append(1 if total_exec_qty > 0 else 0)
        y_edge.append(_to_float(net_edge, float("nan")))

    return {
        "rows": rows,
        "X": np.array(X, dtype=float),
        "y_open": np.array(y_open, dtype=int),
        "y_fill": np.array(y_fill, dtype=int),
        "y_edge": np.array(y_edge, dtype=float),
    }


def load_lifecycle_dataset(
    conn: sqlite3.Connection,
    *,
    target_edge_bps: float,
    limit: int = 200000,
    closed_only: bool = True,
    symbol: str | None = None,
) -> dict[str, Any]:
    ensure_lifecycle_schema(conn)
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        rows = _select_rows(
            conn,
            limit=max(int(limit), 1),
            closed_only=closed_only,
            symbol=symbol.strip().upper() if symbol else None,
        )
    finally:
        conn.row_factory = prev_factory
    return build_matrices_from_rows(rows, target_edge_bps=target_edge_bps)


def get_feature_matrix_and_labels(
    conn: sqlite3.Connection,
    symbol: str,
    limit: int = 50000,
) -> tuple[list[list[float]], list[float]]:
    """
    Backward compatible adapter used by legacy call-sites.
    """
    dataset = load_lifecycle_dataset(
        conn,
        target_edge_bps=0.0,
        limit=limit,
        closed_only=True,
        symbol=symbol,
    )
    X = dataset["X"]
    y_open = dataset["y_open"]
    return X.tolist(), y_open.astype(float).tolist()
