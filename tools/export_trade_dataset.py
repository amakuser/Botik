"""
Export ML-ready trade dataset from Botik lifecycle tables.

One row = one signal_id, enriched with execution aggregates and outcome fields.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Any


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _fetch_exec_agg(conn: sqlite3.Connection) -> dict[str, dict[str, float | int]]:
    if not _table_exists(conn, "executions_raw"):
        return {}
    rows = conn.execute(
        """
        SELECT
            signal_id,
            MIN(exec_time_ms) AS first_exec_time_ms,
            MAX(exec_time_ms) AS last_exec_time_ms,
            SUM(exec_qty) AS total_exec_qty,
            SUM(exec_price * exec_qty) AS total_exec_quote,
            SUM(COALESCE(exec_fee, 0)) AS total_fees_quote
        FROM executions_raw
        WHERE signal_id IS NOT NULL AND signal_id <> ''
        GROUP BY signal_id
        """
    ).fetchall()
    out: dict[str, dict[str, float | int]] = {}
    for row in rows:
        signal_id = str(row[0])
        out[signal_id] = {
            "first_exec_time_ms": int(row[1] or 0),
            "last_exec_time_ms": int(row[2] or 0),
            "total_exec_qty": float(row[3] or 0.0),
            "total_exec_quote": float(row[4] or 0.0),
            "total_fees_quote": float(row[5] or 0.0),
        }
    return out


def _fetch_outcomes(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not _table_exists(conn, "outcomes"):
        return {}
    rows = conn.execute(
        """
        SELECT
            signal_id,
            entry_vwap,
            exit_vwap,
            filled_qty,
            hold_time_ms,
            gross_pnl_quote,
            net_pnl_quote,
            net_edge_bps,
            was_fully_filled,
            was_profitable,
            exit_reason
        FROM outcomes
        """
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[str(row[0])] = {
            "entry_vwap": row[1],
            "exit_vwap": row[2],
            "filled_qty": row[3],
            "hold_time_ms": row[4],
            "gross_pnl_quote": row[5],
            "net_pnl_quote": row[6],
            "net_edge_bps": row[7],
            "was_fully_filled": row[8],
            "was_profitable": row[9],
            "exit_reason": row[10],
        }
    return out


def export_dataset(db_path: Path, out_csv: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        exec_agg = _fetch_exec_agg(conn)
        outcomes = _fetch_outcomes(conn)

        if _table_exists(conn, "signals"):
            signal_rows = conn.execute(
                """
                SELECT
                    signal_id,
                    ts_signal_ms,
                    symbol,
                    side,
                    spread_bps,
                    depth_bid_quote,
                    depth_ask_quote,
                    slippage_buy_bps_est,
                    slippage_sell_bps_est,
                    trades_per_min,
                    p95_trade_gap_ms,
                    vol_1s_bps,
                    min_required_spread_bps,
                    order_size_quote,
                    order_size_base,
                    entry_price
                FROM signals
                ORDER BY ts_signal_ms
                """
            ).fetchall()
        else:
            signal_rows = []

        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "signal_id",
                    "symbol",
                    "side",
                    "ts_signal_ms",
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
                    "entry_price_decision",
                    "entry_fill_time_ms",
                    "entry_fill_ratio",
                    "entry_vwap",
                    "exit_vwap",
                    "hold_time_ms",
                    "total_fees_quote",
                    "net_pnl_quote",
                    "net_edge_bps",
                    "label_open",
                    "label_fill",
                    "exit_reason",
                ],
            )
            writer.writeheader()

            for row in signal_rows:
                signal_id = str(row["signal_id"])
                agg = exec_agg.get(signal_id, {})
                out = outcomes.get(signal_id, {})

                total_exec_qty = float(agg.get("total_exec_qty", 0.0))
                total_exec_quote = float(agg.get("total_exec_quote", 0.0))
                total_fees_quote = float(agg.get("total_fees_quote", 0.0))
                order_size_base = float(row["order_size_base"] or 0.0)

                entry_fill_ratio = (total_exec_qty / order_size_base) if order_size_base > 0 else 0.0
                entry_vwap_exec = (total_exec_quote / total_exec_qty) if total_exec_qty > 0 else None
                entry_vwap = out.get("entry_vwap", entry_vwap_exec)

                was_profitable = out.get("was_profitable")
                label_open = 1 if was_profitable in (1, True) else 0
                label_fill = 1 if total_exec_qty > 0 else 0

                writer.writerow(
                    {
                        "signal_id": signal_id,
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "ts_signal_ms": row["ts_signal_ms"],
                        "spread_bps_at_signal": row["spread_bps"],
                        "depth_bid_quote_at_signal": row["depth_bid_quote"],
                        "depth_ask_quote_at_signal": row["depth_ask_quote"],
                        "slippage_buy_bps_est": row["slippage_buy_bps_est"],
                        "slippage_sell_bps_est": row["slippage_sell_bps_est"],
                        "trades_per_min_at_signal": row["trades_per_min"],
                        "p95_trade_gap_ms_at_signal": row["p95_trade_gap_ms"],
                        "vol_1s_bps_at_signal": row["vol_1s_bps"],
                        "min_required_spread_bps": row["min_required_spread_bps"],
                        "order_size_quote": row["order_size_quote"],
                        "order_size_base": row["order_size_base"],
                        "entry_price_decision": row["entry_price"],
                        "entry_fill_time_ms": agg.get("first_exec_time_ms", 0),
                        "entry_fill_ratio": entry_fill_ratio,
                        "entry_vwap": entry_vwap,
                        "exit_vwap": out.get("exit_vwap"),
                        "hold_time_ms": out.get("hold_time_ms"),
                        "total_fees_quote": total_fees_quote,
                        "net_pnl_quote": out.get("net_pnl_quote"),
                        "net_edge_bps": out.get("net_edge_bps"),
                        "label_open": label_open,
                        "label_fill": label_fill,
                        "exit_reason": out.get("exit_reason"),
                    }
                )

        return len(signal_rows)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ML dataset from lifecycle tables")
    parser.add_argument("--db-path", default="data/botik.db", help="Path to sqlite db")
    parser.add_argument("--out-csv", default="data/ml/trades_dataset.csv", help="Output CSV path")
    args = parser.parse_args()

    rows = export_dataset(Path(args.db_path), Path(args.out_csv))
    print(f"EXPORT_OK rows={rows} out={args.out_csv}")


if __name__ == "__main__":
    main()
