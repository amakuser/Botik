"""Tests for OrderbookMixin (api_orderbook_mixin.py)."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.botik.gui.api_orderbook_mixin import OrderbookMixin, _KEEP_SNAPSHOTS


# ── Minimal stub ─────────────────────────────────────────────────────────────

class _StubAPI(OrderbookMixin):
    """OrderbookMixin without real DB or background thread."""

    def __init__(self) -> None:
        self._ob_symbols = [("BTCUSDT", "linear"), ("ETHUSDT", "linear")]
        self._ob_stop = threading.Event()
        # Do NOT start background thread in tests


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db_with_table(path: Path) -> None:
    """Create a minimal SQLite DB with orderbook_snapshots table."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol         TEXT    NOT NULL,
            category       TEXT    NOT NULL DEFAULT 'linear',
            bids_json      TEXT    NOT NULL,
            asks_json      TEXT    NOT NULL,
            ts_ms          INTEGER NOT NULL,
            created_at_utc TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_snapshot(path: Path, symbol: str, category: str,
                     bids: list, asks: list, ts_ms: int = 1_700_000_000_000) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO orderbook_snapshots (symbol, category, bids_json, asks_json, ts_ms, created_at_utc) "
        "VALUES (?, ?, ?, ?, ?, '2024-01-01T00:00:00+00:00')",
        (symbol, category, json.dumps(bids), json.dumps(asks), ts_ms),
    )
    conn.commit()
    conn.close()


# ── Tests: get_orderbook ─────────────────────────────────────────────────────

class TestGetOrderbook:
    def test_returns_empty_when_no_data(self, tmp_path):
        db = tmp_path / "botik.db"
        _make_db_with_table(db)
        api = _StubAPI()
        with (
            patch("src.botik.gui.api_orderbook_mixin._load_yaml", return_value={}),
            patch("src.botik.gui.api_orderbook_mixin._resolve_db_path", return_value=db),
        ):
            result = json.loads(api.get_orderbook("BTCUSDT", "linear"))
        assert result["symbol"] == "BTCUSDT"
        assert result["category"] == "linear"
        assert result["bids"] == []
        assert result["asks"] == []
        assert result["ts_ms"] is None

    def test_returns_latest_snapshot(self, tmp_path):
        db = tmp_path / "botik.db"
        _make_db_with_table(db)
        bids = [["65000.0", "0.5"], ["64990.0", "1.2"]]
        asks = [["65010.0", "0.3"], ["65020.0", "0.8"]]
        _insert_snapshot(db, "BTCUSDT", "linear", bids, asks, ts_ms=1_700_000_001_000)

        api = _StubAPI()
        with (
            patch("src.botik.gui.api_orderbook_mixin._load_yaml", return_value={}),
            patch("src.botik.gui.api_orderbook_mixin._resolve_db_path", return_value=db),
        ):
            result = json.loads(api.get_orderbook("BTCUSDT", "linear"))

        assert result["symbol"] == "BTCUSDT"
        assert result["bids"] == bids
        assert result["asks"] == asks
        assert result["ts_ms"] == 1_700_000_001_000

    def test_returns_most_recent_by_ts_ms(self, tmp_path):
        db = tmp_path / "botik.db"
        _make_db_with_table(db)
        _insert_snapshot(db, "BTCUSDT", "linear", [["100", "1"]], [["101", "1"]], ts_ms=1000)
        _insert_snapshot(db, "BTCUSDT", "linear", [["200", "2"]], [["201", "2"]], ts_ms=2000)

        api = _StubAPI()
        with (
            patch("src.botik.gui.api_orderbook_mixin._load_yaml", return_value={}),
            patch("src.botik.gui.api_orderbook_mixin._resolve_db_path", return_value=db),
        ):
            result = json.loads(api.get_orderbook("BTCUSDT", "linear"))

        assert result["bids"][0][0] == "200"

    def test_returns_error_on_db_failure(self):
        api = _StubAPI()
        nonexistent = Path("/nonexistent/path/botik.db")
        with (
            patch("src.botik.gui.api_orderbook_mixin._load_yaml", return_value={}),
            patch("src.botik.gui.api_orderbook_mixin._resolve_db_path", return_value=nonexistent),
        ):
            result = json.loads(api.get_orderbook("BTCUSDT", "linear"))
        assert "error" in result


# ── Tests: get_orderbook_symbols ─────────────────────────────────────────────

class TestGetOrderbookSymbols:
    def test_returns_default_symbols(self):
        api = _StubAPI()
        result = json.loads(api.get_orderbook_symbols())
        assert isinstance(result, list)
        assert len(result) == 2
        assert {"symbol": "BTCUSDT", "category": "linear"} in result

    def test_symbols_have_required_keys(self):
        api = _StubAPI()
        result = json.loads(api.get_orderbook_symbols())
        for item in result:
            assert "symbol" in item
            assert "category" in item


# ── Tests: set_orderbook_symbols ─────────────────────────────────────────────

class TestSetOrderbookSymbols:
    def test_updates_tracked_symbols(self):
        api = _StubAPI()
        new_symbols = [{"symbol": "XRPUSDT", "category": "linear"}]
        result = json.loads(api.set_orderbook_symbols(json.dumps(new_symbols)))
        assert result["ok"] is True
        assert result["count"] == 1
        assert api._ob_symbols == [("XRPUSDT", "linear")]

    def test_invalid_json_returns_error(self):
        api = _StubAPI()
        result = json.loads(api.set_orderbook_symbols("not_valid_json"))
        assert result["ok"] is False
        assert "error" in result


# ── Tests: _ob_store (pruning) ───────────────────────────────────────────────

class TestObStore:
    def test_prunes_old_snapshots(self, tmp_path):
        db = tmp_path / "botik.db"
        _make_db_with_table(db)

        api = _StubAPI()
        with (
            patch("src.botik.gui.api_orderbook_mixin._load_yaml", return_value={}),
            patch("src.botik.gui.api_orderbook_mixin._resolve_db_path", return_value=db),
        ):
            # Insert more than _KEEP_SNAPSHOTS
            for i in range(_KEEP_SNAPSHOTS + 5):
                api._ob_store("BTCUSDT", "linear", [["100", "1"]], [["101", "1"]], ts_ms=i)

        conn = sqlite3.connect(str(db))
        count = conn.execute(
            "SELECT COUNT(*) FROM orderbook_snapshots WHERE symbol='BTCUSDT' AND category='linear'"
        ).fetchone()[0]
        conn.close()
        assert count <= _KEEP_SNAPSHOTS
