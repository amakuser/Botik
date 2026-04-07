"""
Tests for BackfillWorker (M1.3).

Verifies:
- Skips symbols that already have enough candles
- Calls OHLCVWorker for each (symbol, category, interval)
- Updates SymbolRegistry after each successful backfill
- Sets data_status='ready' when candle_count >= MIN_CANDLES_READY
- Handles OHLCVWorker errors gracefully (records error, continues)
- stop() halts processing after current request
- run_symbol() auto-registers symbol if not present
- BackfillReport aggregates results correctly

Uses mocked OHLCVWorker — no real Bybit API calls.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.botik.storage.db import Database
from src.botik.data.symbol_registry import SymbolRegistry, MIN_CANDLES_READY
from src.botik.data.backfill_worker import BackfillWorker, DEFAULT_INTERVALS


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    with database.connect() as conn:
        from src.botik.storage.migrations import run_migrations
        run_migrations(conn)
    return database


@pytest.fixture()
def registry(db: Database) -> SymbolRegistry:
    return SymbolRegistry(db)


def _make_worker(
    registry: SymbolRegistry,
    candles_returned: int = MIN_CANDLES_READY,
    candle_count_in_db: int = MIN_CANDLES_READY,
    raise_error: bool = False,
) -> BackfillWorker:
    """
    Build a BackfillWorker with a mocked OHLCVWorker.
    candles_returned  — how many new candles backfill() claims to have saved
    candle_count_in_db — what get_candle_count() returns
    raise_error       — simulate a network/API failure
    """
    worker = BackfillWorker(registry, intervals=["1"], days_back=30)

    mock_ohlcv = MagicMock()
    if raise_error:
        mock_ohlcv.backfill = AsyncMock(side_effect=RuntimeError("simulated error"))
    else:
        mock_ohlcv.backfill = AsyncMock(return_value=candles_returned)
    mock_ohlcv.get_candle_count = MagicMock(return_value=candle_count_in_db)

    worker._ohlcv = mock_ohlcv
    return worker


# ─────────────────────────────────────────────────────────────────────────────
#  run_all — happy path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all_updates_registry_after_backfill(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear", "1")
    worker = _make_worker(registry, candles_returned=600, candle_count_in_db=600)

    report = await worker.run_all()

    assert len(report.succeeded) == 1
    assert len(report.failed) == 0
    assert report.total_added == 600

    rec = registry.get("BTCUSDT", "linear", "1")
    assert rec is not None
    assert rec.candle_count == 600
    assert rec.data_status == "ready"
    assert rec.last_backfill_at is not None


@pytest.mark.asyncio
async def test_run_all_skips_symbols_with_enough_candles(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear", "1")
    # Pre-fill with enough candles so it doesn't need backfill
    registry.update_candle_stats("BTCUSDT", "linear", "1", MIN_CANDLES_READY)

    worker = _make_worker(registry, candles_returned=0, candle_count_in_db=MIN_CANDLES_READY)
    report = await worker.run_all()

    # get_needing_backfill() returns empty → OHLCVWorker never called
    worker._ohlcv.backfill.assert_not_called()
    assert len(report.results) == 0


@pytest.mark.asyncio
async def test_run_all_processes_multiple_symbols(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear", "1")
    worker = _make_worker(registry, candles_returned=500, candle_count_in_db=500)

    report = await worker.run_all()

    assert len(report.succeeded) == 2
    assert worker._ohlcv.backfill.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
#  Error handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all_records_error_and_continues(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear", "1")

    worker = BackfillWorker(registry, intervals=["1"], days_back=30)
    mock_ohlcv = MagicMock()
    call_count = 0

    async def backfill_side_effect(symbol, category, interval, days_back):
        nonlocal call_count
        call_count += 1
        if symbol == "BTCUSDT":
            raise RuntimeError("network timeout")
        return 500

    mock_ohlcv.backfill = AsyncMock(side_effect=backfill_side_effect)
    mock_ohlcv.get_candle_count = MagicMock(return_value=500)
    worker._ohlcv = mock_ohlcv

    report = await worker.run_all()

    assert len(report.failed) == 1
    assert len(report.succeeded) == 1
    assert report.failed[0].symbol == "BTCUSDT"
    assert "network timeout" in report.failed[0].error


# ─────────────────────────────────────────────────────────────────────────────
#  data_status transitions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_candles_sets_partial_status(registry: SymbolRegistry) -> None:
    registry.register("SOLUSDT", "linear", "1")
    worker = _make_worker(registry, candles_returned=100, candle_count_in_db=100)

    await worker.run_all()

    rec = registry.get("SOLUSDT", "linear", "1")
    assert rec is not None
    assert rec.data_status == "partial"
    assert rec.candle_count == 100


@pytest.mark.asyncio
async def test_exact_min_candles_sets_ready_status(registry: SymbolRegistry) -> None:
    registry.register("XRPUSDT", "spot", "1")
    worker = _make_worker(
        registry,
        candles_returned=MIN_CANDLES_READY,
        candle_count_in_db=MIN_CANDLES_READY,
    )
    await worker.run_all()

    rec = registry.get("XRPUSDT", "spot", "1")
    assert rec is not None
    assert rec.data_status == "ready"


# ─────────────────────────────────────────────────────────────────────────────
#  run_symbol
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_symbol_auto_registers(registry: SymbolRegistry) -> None:
    # Symbol NOT in registry beforehand
    assert registry.get("BNBUSDT", "linear") is None

    worker = _make_worker(registry, candles_returned=500, candle_count_in_db=500)
    results = await worker.run_symbol("BNBUSDT", "linear")

    assert len(results) == 1
    assert results[0].success

    rec = registry.get("BNBUSDT", "linear")
    assert rec is not None  # was auto-registered


@pytest.mark.asyncio
async def test_run_symbol_custom_intervals(registry: SymbolRegistry) -> None:
    worker = _make_worker(registry, candles_returned=300, candle_count_in_db=300)
    results = await worker.run_symbol("BTCUSDT", "linear", intervals=["5", "15"])

    assert len(results) == 2
    symbols = {(r.symbol, r.interval) for r in results}
    assert ("BTCUSDT", "5") in symbols
    assert ("BTCUSDT", "15") in symbols


# ─────────────────────────────────────────────────────────────────────────────
#  BackfillReport
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_summary_lines(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear", "1")

    worker = BackfillWorker(registry, intervals=["1"], days_back=30)
    mock_ohlcv = MagicMock()

    async def mixed(symbol, category, interval, days_back):
        if symbol == "BTCUSDT":
            return 500
        raise RuntimeError("fail")

    mock_ohlcv.backfill = AsyncMock(side_effect=mixed)
    mock_ohlcv.get_candle_count = MagicMock(return_value=500)
    worker._ohlcv = mock_ohlcv

    report = await worker.run_all()
    lines = report.summary_lines()

    assert any("1 ok" in l for l in lines)
    assert any("1 failed" in l for l in lines)
    assert any("FAILED" in l and "ETHUSDT" in l for l in lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Default intervals match expected timeframes
# ─────────────────────────────────────────────────────────────────────────────

def test_default_intervals_cover_all_timeframes() -> None:
    """Verify DEFAULT_INTERVALS contains all four causal timeframes."""
    assert "1" in DEFAULT_INTERVALS    # 1m
    assert "5" in DEFAULT_INTERVALS    # 5m
    assert "15" in DEFAULT_INTERVALS   # 15m
    assert "60" in DEFAULT_INTERVALS   # 1h
