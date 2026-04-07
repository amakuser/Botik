"""
Tests for SymbolLabelingRegistry (M0 — per-model labeling status).

Verifies:
- migration creates symbol_labeling_status table with correct columns
- upsert/upsert_many are idempotent
- set_status transitions work correctly
- futures and spot scopes are tracked independently for same symbol
- filtering queries: pending, ready, all
- summary aggregation per model_scope
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.botik.storage.db import Database
from src.botik.data.symbol_labeling_registry import SymbolLabelingRegistry


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path) -> Database:
    db_path = tmp_path / "test_labeling_registry.db"
    database = Database(f"sqlite:///{db_path}")
    with database.connect() as conn:
        from src.botik.storage.migrations import run_migrations
        run_migrations(conn)
    return database


@pytest.fixture()
def reg(db: Database) -> SymbolLabelingRegistry:
    return SymbolLabelingRegistry(db)


# ─────────────────────────────────────────────────────────────────────────────
#  Migration
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_creates_symbol_labeling_status_table(tmp_path: Path) -> None:
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
        assert "symbol_labeling_status" in tables

        cols = {
            row[1]
            for row in raw.execute(
                "PRAGMA table_info(symbol_labeling_status)"
            ).fetchall()
        }
        expected = {
            "symbol", "category", "interval", "model_scope",
            "labeling_status", "labeled_count", "last_labeled_at",
            "added_at_utc", "updated_at_utc",
        }
        assert expected <= cols
    finally:
        raw.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Upsert
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_creates_pending_entry(reg: SymbolLabelingRegistry) -> None:
    reg.upsert("BTCUSDT", "linear", "1", "futures")
    rec = reg.get("BTCUSDT", "linear", "1", "futures")
    assert rec is not None
    assert rec.symbol == "BTCUSDT"
    assert rec.model_scope == "futures"
    assert rec.labeling_status == "pending"
    assert rec.labeled_count == 0
    assert rec.is_ready is False


def test_upsert_is_idempotent(reg: SymbolLabelingRegistry) -> None:
    reg.upsert("BTCUSDT", "linear", "1", "futures")
    reg.upsert("BTCUSDT", "linear", "1", "futures")  # must not raise or duplicate
    all_rec = reg.get_all(model_scope="futures")
    btc = [r for r in all_rec if r.symbol == "BTCUSDT"]
    assert len(btc) == 1


def test_upsert_many(reg: SymbolLabelingRegistry) -> None:
    reg.upsert_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "linear", "1", "futures")
    all_rec = reg.get_all(model_scope="futures")
    symbols = {r.symbol for r in all_rec}
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT"} <= symbols


# ─────────────────────────────────────────────────────────────────────────────
#  Key insight: futures and spot are independent per same symbol
# ─────────────────────────────────────────────────────────────────────────────

def test_futures_and_spot_are_tracked_independently(reg: SymbolLabelingRegistry) -> None:
    """
    BTCUSDT can be fully labeled for futures but still pending for spot.
    Different feature engines → different labeled datasets → independent status.
    """
    reg.upsert("BTCUSDT", "linear", "1", "futures")
    reg.upsert("BTCUSDT", "spot", "1", "spot")

    reg.set_status("BTCUSDT", "linear", "1", "futures", "ready", labeled_count=2244)

    futures_rec = reg.get("BTCUSDT", "linear", "1", "futures")
    spot_rec = reg.get("BTCUSDT", "spot", "1", "spot")

    assert futures_rec is not None
    assert futures_rec.is_ready is True
    assert futures_rec.labeled_count == 2244

    assert spot_rec is not None
    assert spot_rec.is_ready is False
    assert spot_rec.labeling_status == "pending"


# ─────────────────────────────────────────────────────────────────────────────
#  set_status transitions
# ─────────────────────────────────────────────────────────────────────────────

def test_set_status_labeling(reg: SymbolLabelingRegistry) -> None:
    reg.upsert("ETHUSDT", "linear", "1", "futures")
    reg.set_status("ETHUSDT", "linear", "1", "futures", "labeling", labeled_count=0)
    rec = reg.get("ETHUSDT", "linear", "1", "futures")
    assert rec is not None
    assert rec.labeling_status == "labeling"
    assert rec.is_in_progress is True


def test_set_status_ready_sets_last_labeled_at(reg: SymbolLabelingRegistry) -> None:
    reg.upsert("BTCUSDT", "linear", "1", "futures")
    reg.set_status("BTCUSDT", "linear", "1", "futures", "ready", labeled_count=2244)
    rec = reg.get("BTCUSDT", "linear", "1", "futures")
    assert rec is not None
    assert rec.is_ready is True
    assert rec.labeled_count == 2244
    assert rec.last_labeled_at is not None


# ─────────────────────────────────────────────────────────────────────────────
#  Filtering queries
# ─────────────────────────────────────────────────────────────────────────────

def test_get_pending_excludes_ready(reg: SymbolLabelingRegistry) -> None:
    reg.upsert_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "linear", "1", "futures")
    reg.set_status("BTCUSDT", "linear", "1", "futures", "ready", labeled_count=2244)

    pending = reg.get_pending(model_scope="futures")
    symbols = {r.symbol for r in pending}
    assert "BTCUSDT" not in symbols
    assert "ETHUSDT" in symbols
    assert "SOLUSDT" in symbols


def test_get_ready_returns_only_ready(reg: SymbolLabelingRegistry) -> None:
    reg.upsert_many(["BTCUSDT", "ETHUSDT"], "linear", "1", "futures")
    reg.set_status("BTCUSDT", "linear", "1", "futures", "ready", labeled_count=2244)

    ready = reg.get_ready(model_scope="futures")
    symbols = {r.symbol for r in ready}
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" not in symbols


def test_get_all_filtered_by_scope(reg: SymbolLabelingRegistry) -> None:
    reg.upsert("BTCUSDT", "linear", "1", "futures")
    reg.upsert("BTCUSDT", "spot", "1", "spot")

    futures_all = reg.get_all(model_scope="futures")
    spot_all = reg.get_all(model_scope="spot")

    assert all(r.model_scope == "futures" for r in futures_all)
    assert all(r.model_scope == "spot" for r in spot_all)


# ─────────────────────────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_aggregates_by_model_scope(reg: SymbolLabelingRegistry) -> None:
    reg.upsert_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], "linear", "1", "futures")
    reg.upsert_many(["BTCUSDT", "ETHUSDT"], "spot", "1", "spot")

    reg.set_status("BTCUSDT", "linear", "1", "futures", "ready", labeled_count=2244)
    reg.set_status("ETHUSDT", "linear", "1", "futures", "labeling", labeled_count=0)
    reg.set_status("BTCUSDT", "spot", "1", "spot", "ready", labeled_count=2023)

    summary = reg.summary()
    assert "futures" in summary
    assert "spot" in summary

    fut = summary["futures"]
    assert fut["total"] == 3
    assert fut["ready"] == 1
    assert fut["labeling"] == 1
    assert fut["pending"] == 1
    assert fut["total_labeled"] == 2244

    sp = summary["spot"]
    assert sp["total"] == 2
    assert sp["ready"] == 1
    assert sp["pending"] == 1
    assert sp["total_labeled"] == 2023
