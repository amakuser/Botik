"""
Tests for LiveDataWorker (M1.4).

Verifies:
- _parse_candle_row converts valid WS dict → tuple correctly
- _parse_candle_row returns None for invalid/missing fields
- _CategoryKlineWS._handle_message saves confirmed candles via callback
- _CategoryKlineWS._handle_message skips unconfirmed candles
- _CategoryKlineWS._handle_message ignores non-kline topics
- _CategoryKlineWS._kline_topics builds correct topic strings
- LiveDataWorker._on_connected sets ws_active=True in registry
- LiveDataWorker._on_disconnected sets ws_active=False in registry
- LiveDataWorker._refresh_candle_stats updates candle_count in registry
- LiveDataWorker._load_symbols_by_category groups symbols correctly

Uses no real WebSocket — all connectivity mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.botik.storage.db import Database
from src.botik.data.symbol_registry import SymbolRegistry
from src.botik.data.live_data_worker import (
    LiveDataWorker,
    _CategoryKlineWS,
    _parse_candle_row,
    DEFAULT_INTERVALS,
)


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


def _make_kline_msg(
    symbol: str,
    interval: str,
    confirm: bool,
    start: int = 1_700_000_000_000,
    open_: str = "50000.0",
    high: str = "50100.0",
    low: str = "49900.0",
    close: str = "50050.0",
    volume: str = "1.5",
    turnover: str = "75075.0",
) -> str:
    """Build a Bybit kline WS message as JSON string."""
    return json.dumps({
        "topic": f"kline.{interval}.{symbol}",
        "data": [{
            "start": start,
            "end": start + 60_000,
            "interval": interval,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": turnover,
            "confirm": confirm,
            "timestamp": start + 30_000,
        }],
        "ts": start,
        "type": "snapshot",
    })


# ─────────────────────────────────────────────────────────────────────────────
#  _parse_candle_row
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_candle_row_valid() -> None:
    item = {
        "start": 1_700_000_000_000,
        "open": "50000.0",
        "high": "50100.0",
        "low": "49900.0",
        "close": "50050.0",
        "volume": "1.5",
        "turnover": "75075.0",
        "confirm": True,
    }
    row = _parse_candle_row(item)
    assert row is not None
    open_time_ms, open_, high, low, close, volume, turnover = row
    assert open_time_ms == 1_700_000_000_000
    assert open_ == 50000.0
    assert high == 50100.0
    assert low == 49900.0
    assert close == 50050.0
    assert volume == 1.5
    assert turnover == 75075.0


def test_parse_candle_row_missing_start_returns_none() -> None:
    item = {
        "open": "50000.0", "high": "50100.0", "low": "49900.0",
        "close": "50050.0", "volume": "1.5", "turnover": "75075.0",
    }
    assert _parse_candle_row(item) is None


def test_parse_candle_row_invalid_close_returns_none() -> None:
    item = {
        "start": 1_700_000_000_000,
        "open": "50000.0", "high": "50100.0", "low": "49900.0",
        "close": "not_a_number",
        "volume": "1.5", "turnover": "75075.0",
    }
    assert _parse_candle_row(item) is None


def test_parse_candle_row_zero_close_returns_none() -> None:
    item = {
        "start": 1_700_000_000_000,
        "open": "0", "high": "0", "low": "0", "close": "0",
        "volume": "0", "turnover": "0",
    }
    assert _parse_candle_row(item) is None


def test_parse_candle_row_missing_turnover_uses_zero() -> None:
    """turnover is optional — should default to 0.0 if absent."""
    item = {
        "start": 1_700_000_000_000,
        "open": "100.0", "high": "101.0", "low": "99.0", "close": "100.5",
        "volume": "10.0",
        # no "turnover" key
    }
    row = _parse_candle_row(item)
    assert row is not None
    assert row[6] == 0.0  # turnover defaults to 0


# ─────────────────────────────────────────────────────────────────────────────
#  _CategoryKlineWS._handle_message
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_message_confirmed_calls_callback() -> None:
    received: list[tuple] = []

    def on_confirmed(symbol, category, interval, row):
        received.append((symbol, category, interval, row))

    client = _CategoryKlineWS("linear", ["BTCUSDT"], ["1"], on_confirmed)
    client._handle_message(_make_kline_msg("BTCUSDT", "1", confirm=True))

    assert len(received) == 1
    symbol, category, interval, row = received[0]
    assert symbol == "BTCUSDT"
    assert category == "linear"
    assert interval == "1"
    assert row is not None
    assert row[0] == 1_700_000_000_000  # open_time_ms


def test_handle_message_unconfirmed_skips_callback() -> None:
    received: list = []

    client = _CategoryKlineWS("linear", ["BTCUSDT"], ["1"], lambda *a: received.append(a))
    client._handle_message(_make_kline_msg("BTCUSDT", "1", confirm=False))

    assert len(received) == 0


def test_handle_message_ignores_non_kline_topic() -> None:
    received: list = []

    client = _CategoryKlineWS("linear", ["BTCUSDT"], ["1"], lambda *a: received.append(a))
    msg = json.dumps({"topic": "orderbook.1.BTCUSDT", "data": {}, "ts": 123})
    client._handle_message(msg)

    assert len(received) == 0


def test_handle_message_malformed_json_does_not_raise() -> None:
    client = _CategoryKlineWS("linear", ["BTCUSDT"], ["1"], lambda *a: None)
    client._handle_message("not_json_at_all")  # should not raise


def test_handle_message_multiple_items_only_confirmed_saved() -> None:
    received: list = []
    client = _CategoryKlineWS("linear", ["BTCUSDT"], ["1"], lambda *a: received.append(a))

    # Two items in data — only the confirmed one should trigger callback
    msg = json.dumps({
        "topic": "kline.1.BTCUSDT",
        "data": [
            {"start": 1_700_000_000_000, "open": "50000", "high": "50100",
             "low": "49900", "close": "50050", "volume": "1.0",
             "turnover": "50000", "confirm": False},
            {"start": 1_700_000_060_000, "open": "50050", "high": "50200",
             "low": "50000", "close": "50150", "volume": "2.0",
             "turnover": "100300", "confirm": True},
        ],
        "ts": 1_700_000_060_000,
    })
    client._handle_message(msg)

    assert len(received) == 1
    assert received[0][3][0] == 1_700_000_060_000  # only the confirmed candle


# ─────────────────────────────────────────────────────────────────────────────
#  _CategoryKlineWS._kline_topics
# ─────────────────────────────────────────────────────────────────────────────

def test_kline_topics_format() -> None:
    client = _CategoryKlineWS("linear", ["BTCUSDT", "ETHUSDT"], ["1", "5"], lambda *a: None)
    topics = client._kline_topics(["BTCUSDT", "ETHUSDT"])

    assert "kline.1.BTCUSDT" in topics
    assert "kline.5.BTCUSDT" in topics
    assert "kline.1.ETHUSDT" in topics
    assert "kline.5.ETHUSDT" in topics
    assert len(topics) == 4  # 2 symbols × 2 intervals


# ─────────────────────────────────────────────────────────────────────────────
#  LiveDataWorker registry integration
# ─────────────────────────────────────────────────────────────────────────────

def test_on_connected_sets_ws_active(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    worker = LiveDataWorker(registry)

    worker._on_connected("linear", ["BTCUSDT", "ETHUSDT"])

    btc = registry.get("BTCUSDT", "linear")
    eth = registry.get("ETHUSDT", "linear")
    assert btc is not None and btc.ws_active is True
    assert eth is not None and eth.ws_active is True


def test_on_disconnected_clears_ws_active(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    worker = LiveDataWorker(registry)

    worker._on_connected("linear", ["BTCUSDT", "ETHUSDT"])
    worker._on_disconnected("linear", ["BTCUSDT", "ETHUSDT"])

    btc = registry.get("BTCUSDT", "linear")
    assert btc is not None and btc.ws_active is False


def test_load_symbols_by_category(registry: SymbolRegistry) -> None:
    registry.register_many(["BTCUSDT", "ETHUSDT"], "linear")
    registry.register("SOLUSDT", "spot")
    worker = LiveDataWorker(registry)

    by_cat = worker._load_symbols_by_category()

    assert "linear" in by_cat
    assert "spot" in by_cat
    assert set(by_cat["linear"]) == {"BTCUSDT", "ETHUSDT"}
    assert set(by_cat["spot"]) == {"SOLUSDT"}


def test_refresh_candle_stats_updates_registry(registry: SymbolRegistry) -> None:
    registry.register("BTCUSDT", "linear", "1")
    worker = LiveDataWorker(registry)

    mock_ohlcv = MagicMock()
    mock_ohlcv.get_candle_count = MagicMock(return_value=1200)
    worker._ohlcv = mock_ohlcv

    worker._refresh_candle_stats()

    rec = registry.get("BTCUSDT", "linear", "1")
    assert rec is not None
    assert rec.candle_count == 1200


# ─────────────────────────────────────────────────────────────────────────────
#  Default intervals
# ─────────────────────────────────────────────────────────────────────────────

def test_default_intervals_present() -> None:
    assert "1"  in DEFAULT_INTERVALS
    assert "5"  in DEFAULT_INTERVALS
    assert "15" in DEFAULT_INTERVALS
    assert "60" in DEFAULT_INTERVALS
