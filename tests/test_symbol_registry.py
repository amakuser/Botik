"""
Tests for SymbolRegistry (M0 — raw OHLCV data tracking).

Verifies:
- migration creates the table with correct columns (no labeling columns)
- register/register_many are idempotent
- candle stats update recalculates data_status correctly
- ws_active writes and reads back
- filtering queries: needing_backfill, ready, ws_active
- summary aggregation per category
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.botik.storage.db import Database
from src.botik.data.symbol_registry import SymbolRegistry, MIN_CANDLES_READY


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path) -> Database:
    db_path = tmp_path / "test_registry.db"
    database = Database(f"sqlite:///{db_path}")
    with database.connect() as conn:
        from src.botik.storage.migrations import run_migrations
        run_migrations(conn)
    return database


@pytest.fixture()
def registry(db: Database) -> SymbolRegistry:
    return SymbolRegistry(db)


# ─────────────────────────────────────────────────────────────────────────────
#  Migration
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_creates_symbol_registry_table(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_check.db"
    raw = sqlite3.connect(str(db_path))
    try:
        database = Database(f"sqlite:///{db_path}")
        with database.connect() as conn:
            from src.botik.storage.migrations import run_migrations
            run_migrations(conn)

        tables = {
            row[0]
            for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "symbol_registry" in tables

        cols = {
            row[1]
            for row in raw.execute("PRAGMA table_info(symbol_registry)").fetchall()
        }
        # Must have raw-data columns
        expected = {
            "symbol", "category", "interval", "candle_count", "last_candle_ms",
            "last_backfill_at", "ws_active", "data_status",
            "added_at_utc", "updated_at_utc",
        }
        assert expected <= cols

        # Must NOT contain labeling columns (those live in symbol_labeling_status)
        assert "labeling_status" not in cols
        assert "labeled_count" not in cols
    finally:
        raw.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Register
# ─────────────────────────────────────────────────────────────────────────────

def test_register_adds_new_symbol(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear")
    rec = registry.get("BTCUSDT", "linear")
    assert rec is not None
    assert rec.symbol == "BTCUSDT"
    assert rec.category == "linear"
    assert rec.candle_count == 0
    assert rec.data_status == "empty"
    assert rec.ws_active is False


def test_register_is_idempotent(registry: SymbolRegistry) -> None:
    registry.register("ETHUSDT", "spot")
    registry.register("ETHUSDT", "spot")
    all_records = registry.get_all(category="spot")
    eth_records = [r for r in all_records if r.symbol == "ETHUSDT"]
    assert len(eth_records) == 1


def test_register_many(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "linear")
    all_records = registry.get_all(category="linear")
    symbols = {r.symbol for r in all_records}
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT"} <= symbols


# ─────────────────────────────────────────────────────────────────────────────
#  Candle stats + data_status
# ─────────────────────────────────────────────────────────────────────────────

def test_update_candle_stats_sets_partial_status(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear")
    registry.update_candle_stats("BTCUSDT", "linear", "1", candle_count=100)
    rec = registry.get("BTCUSDT", "linear")
    assert rec is not None
    assert rec.candle_count == 100
    assert rec.data_status == "partial"


def test_update_candle_stats_sets_ready_status(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear")
    registry.update_candle_stats(
        "BTCUSDT", "linear", "1",
        candle_count=MIN_CANDLES_READY,
        last_candle_ms=1_700_000_000_000,
        last_backfill_at="2026-03-22T10:00:00Z",
    )
    rec = registry.get("BTCUSDT", "linear")
    assert rec is not None
    assert rec.data_status == "ready"
    assert rec.last_candle_ms == 1_700_000_000_000
    assert rec.last_backfill_at == "2026-03-22T10:00:00Z"
    assert rec.is_ready_for_labeling is True


def test_zero_candles_is_empty_status(registry: SymbolRegistry) -> None:
    registry.register("SOLUSDT", "spot")
    registry.update_candle_stats("SOLUSDT", "spot", "1", candle_count=0)
    rec = registry.get("SOLUSDT", "spot")
    assert rec is not None
    assert rec.data_status == "empty"


# ─────────────────────────────────────────────────────────────────────────────
#  WebSocket active flag
# ─────────────────────────────────────────────────────────────────────────────

def test_set_ws_active_true(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear")
    registry.set_ws_active("BTCUSDT", "linear", active=True)
    rec = registry.get("BTCUSDT", "linear")
    assert rec is not None
    assert rec.ws_active is True


def test_set_ws_active_false(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear")
    registry.set_ws_active("BTCUSDT", "linear", active=True)
    registry.set_ws_active("BTCUSDT", "linear", active=False)
    rec = registry.get("BTCUSDT", "linear")
    assert rec is not None
    assert rec.ws_active is False


# ─────────────────────────────────────────────────────────────────────────────
#  Filtering queries
# ─────────────────────────────────────────────────────────────────────────────

def test_get_needing_backfill_returns_low_candle_symbols(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    registry.update_candle_stats("BTCUSDT", "linear", "1", candle_count=MIN_CANDLES_READY)
    registry.update_candle_stats("ETHUSDT", "linear", "1", candle_count=100)

    needing = registry.get_needing_backfill(category="linear")
    symbols = {r.symbol for r in needing}
    assert "ETHUSDT" in symbols
    assert "BTCUSDT" not in symbols


def test_get_ready_returns_only_ready_symbols(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "linear")
    registry.update_candle_stats("BTCUSDT", "linear", "1", candle_count=MIN_CANDLES_READY)
    registry.update_candle_stats("ETHUSDT", "linear", "1", candle_count=100)

    ready = registry.get_ready(category="linear")
    symbols = {r.symbol for r in ready}
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" not in symbols
    assert "SOLUSDT" not in symbols


def test_get_ws_active_filters_correctly(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    registry.set_ws_active("BTCUSDT", "linear", active=True)

    active = registry.get_ws_active(category="linear")
    symbols = {r.symbol for r in active}
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" not in symbols


# ─────────────────────────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_aggregates_by_category(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    registry.register("SOLUSDT", "spot")

    registry.update_candle_stats("BTCUSDT", "linear", "1", candle_count=MIN_CANDLES_READY)
    registry.update_candle_stats("ETHUSDT", "linear", "1", candle_count=100)
    registry.set_ws_active("BTCUSDT", "linear", active=True)
    registry.set_ws_active("ETHUSDT", "linear", active=True)

    summary = registry.summary()
    assert "linear" in summary
    assert "spot" in summary

    lin = summary["linear"]
    assert lin["total"] == 2
    assert lin["ready"] == 1
    assert lin["partial"] == 1
    assert lin["ws_active"] == 2

    sp = summary["spot"]
    assert sp["total"] == 1
    assert sp["empty"] == 1
