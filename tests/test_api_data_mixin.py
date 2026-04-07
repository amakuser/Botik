"""
Tests for DataMixin (M4) — get_data_status and worker state controls.

Verifies:
- get_data_status() returns valid JSON with symbols, summary, worker states
- symbols list reflects symbol_registry contents
- summary has per-category counts (ready, total, ws_active, total_candles)
- backfill_state and livedata_state reflect ManagedProcess.state
- start_backfill / stop_backfill toggle button visibility logic
- start_live_data / stop_live_data toggle button visibility logic
- empty symbol_registry returns empty symbols and summary
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.data.symbol_registry import SymbolRegistry
from src.botik.gui.api_data_mixin import DataMixin


# ─────────────────────────────────────────────────────────────────────────────
#  Minimal stub that satisfies DataMixin's requirements
# ─────────────────────────────────────────────────────────────────────────────

class _StubAPI(DataMixin):
    """Minimal test double for DashboardAPI that includes DataMixin."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._backfill_process = MagicMock()
        self._backfill_process.state = "stopped"
        self._backfill_process.running = False
        self._livedata_process = MagicMock()
        self._livedata_process.state = "stopped"
        self._livedata_process.running = False
        self._log_entries: list[str] = []

    # DbMixin stubs used by DataMixin
    def _db_connect(self, db_path):
        import sqlite3
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=3, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, conn, table_name: str) -> bool:
        try:
            conn.execute(f"SELECT 1 FROM {table_name} WHERE 1=0").fetchall()
            return True
        except Exception:
            return False

    def _add_log(self, msg: str, channel: str = "sys") -> None:
        self._log_entries.append(msg)


def _make_db(tmp_path: Path) -> tuple[Database, Path]:
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path}")
    with db.connect() as conn:
        run_migrations(conn)
    return db, db_path


def _patch_load_yaml(db_path: Path):
    """Patch _load_yaml and _resolve_db_path to point to test DB."""
    import src.botik.gui.api_data_mixin as m
    orig_load  = m._load_yaml
    orig_resol = m._resolve_db_path

    def _fake_load():  return {}
    def _fake_resol(_): return db_path

    return (
        patch.object(m, "_load_yaml",       _fake_load),
        patch.object(m, "_resolve_db_path",  _fake_resol),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_data_status_empty_registry(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)

    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        raw = api.get_data_status()

    data = json.loads(raw)
    assert "symbols" in data
    assert "summary" in data
    assert "backfill_state" in data
    assert "livedata_state" in data
    assert data["symbols"] == []
    assert data["summary"] == {}
    assert data["backfill_state"] == "stopped"
    assert data["livedata_state"] == "stopped"


def test_get_data_status_with_symbols(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    registry = SymbolRegistry(db)
    registry.register("BTCUSDT", "linear", "1")
    registry.register("ETHUSDT", "linear", "1")
    registry.register("SOLUSDT", "spot",   "1")
    registry.update_candle_stats("BTCUSDT", "linear", "1", 1200, last_candle_ms=None)
    registry.update_candle_stats("ETHUSDT", "linear", "1", 200,  last_candle_ms=None)

    api = _StubAPI(db_path)
    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        raw = api.get_data_status()

    data = json.loads(raw)
    assert len(data["symbols"]) == 3
    summary = data["summary"]
    assert "linear" in summary
    assert "spot"   in summary
    assert summary["linear"]["total"] == 2
    assert summary["linear"]["ready"] == 1    # BTCUSDT (1200 >= 500)
    assert summary["linear"]["partial"] == 1  # ETHUSDT (200 < 500 > 0)
    assert summary["spot"]["total"] == 1
    assert summary["spot"]["empty"] == 1      # SOLUSDT (0 candles)


def test_get_data_status_total_candles(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    registry = SymbolRegistry(db)
    registry.register("BTCUSDT", "linear", "1")
    registry.register("SOLUSDT", "spot", "1")
    registry.update_candle_stats("BTCUSDT", "linear", "1", 5000)
    registry.update_candle_stats("SOLUSDT", "spot",   "1", 3000)

    api = _StubAPI(db_path)
    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        data = json.loads(api.get_data_status())

    assert data["summary"]["linear"]["total_candles"] == 5000
    assert data["summary"]["spot"]["total_candles"]   == 3000


def test_get_data_status_ws_active_count(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    registry = SymbolRegistry(db)
    registry.register("BTCUSDT", "linear", "1")
    registry.register("ETHUSDT", "linear", "1")
    registry.set_ws_active("BTCUSDT", "linear", True, "1")

    api = _StubAPI(db_path)
    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        data = json.loads(api.get_data_status())

    assert data["summary"]["linear"]["ws_active"] == 1


def test_get_data_status_worker_states(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    api._backfill_process.state = "running"
    api._livedata_process.state = "stopped"

    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        data = json.loads(api.get_data_status())

    assert data["backfill_state"] == "running"
    assert data["livedata_state"] == "stopped"


def test_start_backfill_when_not_running(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    api._backfill_process.running = False
    api._backfill_process.start.return_value = (True, "ok")

    res = json.loads(api.start_backfill())

    assert res["ok"] is True
    api._backfill_process.start.assert_called_once()


def test_start_backfill_already_running(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    api._backfill_process.running = True

    res = json.loads(api.start_backfill())

    assert res["ok"] is False
    assert res["error"] == "already_running"
    api._backfill_process.start.assert_not_called()


def test_stop_backfill(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)

    res = json.loads(api.stop_backfill())

    assert res["ok"] is True
    api._backfill_process.stop.assert_called_once()


def test_start_live_data_when_not_running(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    api._livedata_process.running = False
    api._livedata_process.start.return_value = (True, "ok")

    res = json.loads(api.start_live_data())

    assert res["ok"] is True
    api._livedata_process.start.assert_called_once()


def test_start_live_data_already_running(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    api._livedata_process.running = True

    res = json.loads(api.start_live_data())

    assert res["ok"] is False
    assert res["error"] == "already_running"


def test_stop_live_data(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)

    res = json.loads(api.stop_live_data())

    assert res["ok"] is True
    api._livedata_process.stop.assert_called_once()


def test_symbol_record_fields_present(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    registry = SymbolRegistry(db)
    registry.register("XRPUSDT", "spot", "5")

    api = _StubAPI(db_path)
    p1, p2 = _patch_load_yaml(db_path)
    with p1, p2:
        data = json.loads(api.get_data_status())

    sym = data["symbols"][0]
    assert sym["symbol"]       == "XRPUSDT"
    assert sym["category"]     == "spot"
    assert sym["interval"]     == "5"
    assert sym["candle_count"] == 0
    assert sym["ws_active"]    is False
    assert sym["data_status"]  == "empty"
