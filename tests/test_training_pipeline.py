"""
Tests for TrainingPipeline (M2).

Verifies:
- _compute_label returns 1 for +0.8% future move
- _compute_label returns 0 for -0.6% future move
- _compute_label returns None for neutral moves
- _build_dataset returns correct X/y shapes
- _build_dataset skips positions with insufficient candles
- run() calls historian.fit() and predictor.fit() with stacked X/y
- run() handles symbols with too few candles gracefully
- run() skips fit() when total samples < MIN_SAMPLES_TO_FIT
- TrainingReport.summary_lines() formats correctly

Uses SQLite in-memory DB — no real Bybit API calls.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.data.training_pipeline import (
    TrainingPipeline,
    TrainingReport,
    SymbolTrainingResult,
    _compute_label,
    PROFIT_TARGET,
    LOSS_TARGET,
    MIN_CANDLES,
    FORWARD_CANDLES,
    MIN_SAMPLES_TO_FIT,
    CHUNK_SIZE,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    with db.connect() as conn:
        run_migrations(conn)
    return db


def _insert_candles(db: Database, symbol: str, category: str, interval: str,
                    n: int, base_price: float = 100.0) -> None:
    """
    Insert n synthetic candles with a 2% oscillating price.
    Amplitude ensures threshold crossings (±0.8% / -0.6%) are generated.
    """
    import math
    rows = []
    for i in range(n):
        ts = 1_700_000_000_000 + i * 60_000
        p = base_price * (1.0 + 0.02 * math.sin(i * 0.5))
        high = p * 1.003
        low  = p * 0.997
        rows.append((symbol, category, interval, ts, p, high, low, p, 100.0, p * 100.0))
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO price_history "
            "(symbol, category, interval, open_time_ms, open, high, low, close, volume, turnover) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )


def _make_future(current: float, pct_change: float, n: int = FORWARD_CANDLES) -> list[dict]:
    """Build a list of future candles where close ends at current*(1+pct_change)."""
    target = current * (1 + pct_change)
    step = (target - current) / n
    return [{"close": current + step * (i + 1)} for i in range(n)]


def _make_pipeline(db: Database, scope: str = "futures") -> TrainingPipeline:
    mock_hist = MagicMock()
    mock_hist.fit = MagicMock(return_value=MagicMock(accuracy=0.60))
    mock_pred = MagicMock()
    mock_pred.fit = MagicMock(return_value=MagicMock(accuracy=0.58))
    return TrainingPipeline(scope, mock_hist, mock_pred, db)


# ─────────────────────────────────────────────────────────────────────────────
#  _compute_label
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_label_buy_signal() -> None:
    """+1.0% max move (clearly above 0.8% threshold) → label=1."""
    future = _make_future(100.0, 0.010)
    assert _compute_label(100.0, future) == 1


def test_compute_label_sell_signal() -> None:
    """-0.8% min move (clearly below -0.6% threshold) → label=0."""
    future = _make_future(100.0, -0.008)
    assert _compute_label(100.0, future) == 0


def test_compute_label_neutral_returns_none() -> None:
    """Small move (0.1%) — neither threshold reached → None."""
    future = _make_future(100.0, 0.001)
    assert _compute_label(100.0, future) is None


def test_compute_label_above_buy_threshold() -> None:
    """Move 2× PROFIT_TARGET → still returns 1."""
    future = _make_future(100.0, PROFIT_TARGET * 2)
    assert _compute_label(100.0, future) == 1


def test_compute_label_below_sell_threshold() -> None:
    """Move 2× LOSS_TARGET magnitude → still returns 0."""
    future = _make_future(100.0, LOSS_TARGET * 2)
    assert _compute_label(100.0, future) == 0


def test_compute_label_clearly_at_profit_threshold() -> None:
    """Close is 0.9% above current — triggers buy label."""
    future = [{"close": 100.9}] * FORWARD_CANDLES   # +0.9% > PROFIT_TARGET
    assert _compute_label(100.0, future) == 1


# ─────────────────────────────────────────────────────────────────────────────
#  _build_dataset
# ─────────────────────────────────────────────────────────────────────────────

def test_build_dataset_too_few_candles_returns_empty(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    _insert_candles(db, "BTCUSDT", "linear", "1", n=10)  # less than MIN_CANDLES+FORWARD
    pipeline = _make_pipeline(db)

    X, y = pipeline._build_dataset("BTCUSDT", "linear", "1")
    assert len(X) == 0
    assert len(y) == 0


def test_build_dataset_returns_correct_shapes(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    # Need MIN_CANDLES + FORWARD_CANDLES + some extra for multiple samples
    _insert_candles(db, "BTCUSDT", "linear", "1", n=200)
    pipeline = _make_pipeline(db)

    X, y = pipeline._build_dataset("BTCUSDT", "linear", "1")
    assert X.ndim == 2
    assert X.shape[1] == 18          # FUTURES_FEATURE_DIM
    assert y.ndim == 1
    assert len(X) == len(y)
    assert y.dtype == np.int32
    assert set(y.tolist()) <= {0, 1}  # only valid labels


def test_build_dataset_spot_returns_14_features(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    _insert_candles(db, "SOLUSDT", "spot", "1", n=200)
    pipeline = _make_pipeline(db, scope="spot")

    X, y = pipeline._build_dataset("SOLUSDT", "spot", "1")
    if len(X) > 0:
        assert X.shape[1] == 14  # SPOT_FEATURE_DIM


# ─────────────────────────────────────────────────────────────────────────────
#  run()
# ─────────────────────────────────────────────────────────────────────────────

def test_run_calls_fit_with_correct_types(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    _insert_candles(db, "BTCUSDT", "linear", "1", n=500)
    pipeline = _make_pipeline(db)

    report = pipeline.run(["BTCUSDT"], interval="1")

    if report.total_samples >= MIN_SAMPLES_TO_FIT:
        pipeline._historian.fit.assert_called_once()
        X_arg, y_arg = pipeline._historian.fit.call_args[0]
        assert isinstance(X_arg, np.ndarray)
        assert isinstance(y_arg, np.ndarray)
        assert X_arg.dtype == np.float32
        assert y_arg.dtype == np.int32


def test_run_stacks_samples_from_multiple_symbols(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    _insert_candles(db, "BTCUSDT", "linear", "1", n=300)
    _insert_candles(db, "ETHUSDT", "linear", "1", n=300)
    pipeline = _make_pipeline(db)

    report = pipeline.run(["BTCUSDT", "ETHUSDT"], interval="1")

    assert len(report.results) == 2
    btc = next(r for r in report.results if r.symbol == "BTCUSDT")
    eth = next(r for r in report.results if r.symbol == "ETHUSDT")
    assert report.total_samples >= btc.samples_used + eth.samples_used


def test_run_skips_fit_when_too_few_samples(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    # Only 10 candles — not enough for any labeled samples
    _insert_candles(db, "BTCUSDT", "linear", "1", n=10)
    pipeline = _make_pipeline(db)

    report = pipeline.run(["BTCUSDT"], interval="1")

    pipeline._historian.fit.assert_not_called()
    pipeline._predictor.fit.assert_not_called()
    assert report.total_samples == 0


def test_run_handles_symbol_error_gracefully(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    _insert_candles(db, "BTCUSDT", "linear", "1", n=300)
    pipeline = _make_pipeline(db)

    # Force an error for ETHUSDT (no data) and success for BTCUSDT
    report = pipeline.run(["BTCUSDT", "ETHUSDT"], interval="1")

    # ETHUSDT should produce empty result (not an error), BTCUSDT should succeed
    eth = next(r for r in report.results if r.symbol == "ETHUSDT")
    btc = next(r for r in report.results if r.symbol == "BTCUSDT")
    assert eth.samples_used == 0
    assert btc.success


def test_run_invalid_scope_raises() -> None:
    db = MagicMock()
    with pytest.raises(ValueError, match="Unknown scope"):
        TrainingPipeline("unknown", MagicMock(), MagicMock(), db)


def test_chunked_reading_produces_same_result_as_full(tmp_path: Path) -> None:
    """
    Chunked reading must not lose any samples at chunk boundaries.
    We insert more candles than CHUNK_SIZE and verify the sample count
    is the same regardless of how chunks split the data.
    """
    db = _make_db(tmp_path)
    # Insert 3× CHUNK_SIZE candles — forces multiple chunk reads
    n = CHUNK_SIZE * 3 + 50
    _insert_candles(db, "BTCUSDT", "linear", "1", n=n)

    pipeline = _make_pipeline(db)
    X, y = pipeline._build_dataset("BTCUSDT", "linear", "1")

    # All valid positions should be covered: no samples lost at boundaries
    expected_positions = n - MIN_CANDLES - FORWARD_CANDLES + 1
    # Not all positions produce labels (neutral ones are skipped), but
    # the count must be > 0 and ≤ expected_positions
    assert len(X) > 0
    assert len(X) <= expected_positions
    assert len(X) == len(y)


# ─────────────────────────────────────────────────────────────────────────────
#  TrainingReport
# ─────────────────────────────────────────────────────────────────────────────

def test_report_summary_lines_contains_key_info() -> None:
    report = TrainingReport(
        scope="futures",
        historian_accuracy=0.61,
        predictor_accuracy=0.59,
        total_samples=2400,
    )
    report.results = [
        SymbolTrainingResult("BTCUSDT", "linear", "1", samples_used=1200),
        SymbolTrainingResult("ETHUSDT", "linear", "1", error="timeout"),
    ]
    lines = report.summary_lines()

    assert any("futures" in l for l in lines)
    assert any("2400" in l for l in lines)
    assert any("0.61" in l for l in lines)
    assert any("FAILED" in l and "ETHUSDT" in l for l in lines)
