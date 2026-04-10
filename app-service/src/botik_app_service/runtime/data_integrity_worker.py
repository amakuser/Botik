from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import traceback
from pathlib import Path

from botik_app_service.runtime.data_backfill_adapter import to_legacy_interval


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def _emit_log(level: str, message: str) -> None:
    _emit({"type": "log", "level": level.upper(), "message": message})


def _emit_progress(
    *,
    progress: float,
    message: str,
    phase: str,
    symbol: str,
    category: str,
    interval: str,
    completed_units: int | None = None,
    total_units: int | None = None,
    rows_written: int | None = None,
) -> None:
    _emit(
        {
            "type": "progress",
            "progress": round(progress, 4),
            "message": message,
            "phase": phase,
            "symbol": symbol,
            "category": category,
            "interval": interval,
            "completed_units": completed_units,
            "total_units": total_units,
            "rows_written": rows_written,
        }
    )


def validate_data_integrity(db_path: Path, *, symbol: str, category: str, interval: str) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"Data backfill DB not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('price_history', 'symbol_registry')"
            ).fetchall()
        }
        if {"price_history", "symbol_registry"} - tables:
            raise ValueError("Required data integrity tables are missing.")

        registry_row = connection.execute(
            """
            SELECT candle_count, last_candle_ms
            FROM symbol_registry
            WHERE symbol=? AND category=? AND interval=?
            """,
            (symbol, category, interval),
        ).fetchone()
        if registry_row is None:
            raise ValueError(f"symbol_registry row missing for {symbol}/{category}/{interval}")
        registry_count, registry_last_candle_ms = int(registry_row[0]), int(registry_row[1])

        history_row = connection.execute(
            """
            SELECT COUNT(*), MIN(open_time_ms), MAX(open_time_ms)
            FROM price_history
            WHERE symbol=? AND category=? AND interval=?
            """,
            (symbol, category, interval),
        ).fetchone()
        history_count = int(history_row[0])
        min_open_time_ms = int(history_row[1]) if history_row[1] is not None else None
        max_open_time_ms = int(history_row[2]) if history_row[2] is not None else None
        if history_count <= 0 or min_open_time_ms is None or max_open_time_ms is None:
            raise ValueError(f"price_history has no candles for {symbol}/{category}/{interval}")

        duplicate_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT open_time_ms
                    FROM price_history
                    WHERE symbol=? AND category=? AND interval=?
                    GROUP BY open_time_ms
                    HAVING COUNT(*) > 1
                )
                """,
                (symbol, category, interval),
            ).fetchone()[0]
        )

    if duplicate_count > 0:
        raise ValueError(f"Found duplicate candles for {symbol}/{category}/{interval}")
    if registry_count != history_count:
        raise ValueError(
            f"symbol_registry candle_count={registry_count} does not match price_history count={history_count}"
        )
    if registry_last_candle_ms != max_open_time_ms:
        raise ValueError(
            f"symbol_registry last_candle_ms={registry_last_candle_ms} does not match price_history max={max_open_time_ms}"
        )

    return {
        "history_count": history_count,
        "registry_count": registry_count,
        "min_open_time_ms": min_open_time_ms,
        "max_open_time_ms": max_open_time_ms,
        "duplicate_count": duplicate_count,
    }


def _resolve_db_path(db_url: str) -> Path:
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        raise ValueError(f"Unsupported DB URL: {db_url}")
    return Path(db_url[len(prefix) :])


def _run(args: argparse.Namespace) -> int:
    symbol = args.symbol.upper()
    category = args.category.lower()
    intervals = [str(interval) for interval in args.intervals]
    if symbol != "BTCUSDT":
        raise ValueError(f"Unsupported integrity symbol: {symbol}")
    if category != "spot":
        raise ValueError(f"Unsupported integrity category: {category}")
    if intervals != ["1m"]:
        raise ValueError(f"Unsupported integrity intervals: {intervals}")

    legacy_interval = to_legacy_interval("1m")
    db_path = _resolve_db_path(args.db_url)

    _emit_progress(
        progress=0.05,
        message="Preparing data integrity validation.",
        phase="preparing",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=0,
        total_units=4,
        rows_written=0,
    )
    _emit_log("INFO", f"Opening data backfill DB at {db_path}.")

    _emit_progress(
        progress=0.2,
        message="Validating data backfill DB presence and schema.",
        phase="opening_db",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=1,
        total_units=4,
        rows_written=0,
    )

    summary = validate_data_integrity(db_path, symbol=symbol, category=category, interval=legacy_interval)
    _emit_log("INFO", f"Validated symbol_registry candle_count={summary['registry_count']} for {symbol}/{category}/1m.")
    _emit_progress(
        progress=0.55,
        message="Validated symbol_registry and price_history counts.",
        phase="validating_counts",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=2,
        total_units=4,
        rows_written=summary["history_count"],
    )
    _emit_log(
        "INFO",
        f"Validated chronological range {summary['min_open_time_ms']}..{summary['max_open_time_ms']} with no duplicates.",
    )
    _emit_progress(
        progress=0.85,
        message="Validated chronological ordering and duplicate constraints.",
        phase="validating_history",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=3,
        total_units=4,
        rows_written=summary["history_count"],
    )
    _emit_progress(
        progress=1.0,
        message="Data integrity validation complete.",
        phase="completed",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=4,
        total_units=4,
        rows_written=summary["history_count"],
    )
    _emit_log("INFO", f"Data integrity check completed: validated {summary['history_count']} candles.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--intervals", nargs="+", required=True)
    parser.add_argument("--db-url", required=True)
    args = parser.parse_args()

    try:
        return _run(args)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
