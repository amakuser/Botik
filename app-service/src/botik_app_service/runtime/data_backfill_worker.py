from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

from botik_app_service.runtime.data_backfill_adapter import FixtureBackfillOHLCVWorker, to_legacy_interval

BATCH_DELAY_SECONDS = 0.25


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


async def _run(args: argparse.Namespace) -> int:
    symbol = args.symbol.upper()
    category = args.category.lower()
    intervals = [str(interval) for interval in args.intervals]
    if symbol != "BTCUSDT":
        raise ValueError(f"Unsupported symbol: {symbol}")
    if category != "spot":
        raise ValueError(f"Unsupported category: {category}")
    if intervals != ["1m"]:
        raise ValueError(f"Unsupported intervals: {intervals}")
    if args.source != "fixture":
        raise ValueError(f"Unsupported source: {args.source}")

    os.environ["DB_URL"] = args.db_url

    _emit_progress(
        progress=0.05,
        message="Preparing data backfill worker.",
        phase="preparing",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=0,
        total_units=4,
        rows_written=0,
    )

    from src.botik.data.backfill_worker import BackfillWorker
    from src.botik.data.symbol_registry import SymbolRegistry
    from src.botik.storage.schema import bootstrap_db

    db = bootstrap_db(args.db_url)
    _emit_log("INFO", "Bootstrapped DB for BTCUSDT/spot/1m.")
    _emit_progress(
        progress=0.1,
        message="Database bootstrapped and ready.",
        phase="bootstrapping_db",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=0,
        total_units=4,
        rows_written=0,
    )

    registry = SymbolRegistry(db)
    worker = BackfillWorker(registry, intervals=[to_legacy_interval("1m")], days_back=1)

    def on_batch(
        batch_symbol: str,
        batch_category: str,
        batch_interval: str,
        completed_units: int,
        total_units: int,
        rows_written: int,
    ) -> None:
        time.sleep(BATCH_DELAY_SECONDS)
        _emit_log("INFO", f"Fetched batch {completed_units}/{total_units} for {batch_symbol}/{batch_category}/{batch_interval}.")
        _emit_progress(
            progress=0.1 + (0.8 * (completed_units / max(total_units, 1))),
            message=f"Fetched {completed_units}/{total_units} batches.",
            phase="running_backfill",
            symbol=batch_symbol,
            category=batch_category,
            interval=batch_interval,
            completed_units=completed_units,
            total_units=total_units,
            rows_written=rows_written,
        )

    worker._ohlcv = FixtureBackfillOHLCVWorker(Path(args.fixture), on_batch=on_batch)
    _emit_log("INFO", "Starting data backfill for BTCUSDT/spot/1m.")
    results = await worker.run_symbol(symbol, category, intervals=[to_legacy_interval("1m")])

    failed = [result for result in results if result.error]
    if failed:
        for result in failed:
            _emit_log("ERROR", f"Backfill failed for {result.symbol}/{result.category}/1m: {result.error}")
        return 1

    rows_written = sum(result.candles_added for result in results)
    _emit_progress(
        progress=1.0,
        message="Backfill complete.",
        phase="completed",
        symbol=symbol,
        category=category,
        interval="1m",
        completed_units=4,
        total_units=4,
        rows_written=rows_written,
    )
    _emit_log("INFO", f"Data backfill completed: wrote {rows_written} candles.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--intervals", nargs="+", required=True)
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--fixture", required=True)
    args = parser.parse_args()

    try:
        return asyncio.run(_run(args))
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
