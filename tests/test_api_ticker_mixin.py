"""Tests for TickerMixin (api_ticker_mixin.py)."""
from __future__ import annotations

import json
import threading
import time

import pytest

from src.botik.gui.api_ticker_mixin import TickerMixin, _DEFAULT_SYMBOLS, _STALE_THRESHOLD_MS


# ── Helper stub ──────────────────────────────────────────────────────────────

class _StubAPI(TickerMixin):
    """Minimal class that exposes TickerMixin without starting a real WS."""

    def __init__(self) -> None:
        # Initialise state manually without starting the real thread
        self._ticker_cache: dict = {}
        self._ticker_lock = threading.Lock()
        self._ticker_symbols: list[str] = list(_DEFAULT_SYMBOLS)
        self._ticker_stop = threading.Event()


def _inject(api: _StubAPI, symbol: str, price: str, change_pct: str, ts: int | None = None) -> None:
    """Directly inject a ticker entry into the cache (simulates WS message)."""
    with api._ticker_lock:
        api._ticker_cache[symbol] = {
            "symbol": symbol,
            "price": price,
            "change_pct": change_pct,
            "ts": ts if ts is not None else int(time.time() * 1000),
        }


# ── Tests ────────────────────────────────────────────────────────────────────

class TestGetLiveTickers:
    def test_returns_all_default_symbols(self):
        api = _StubAPI()
        result = json.loads(api.get_live_tickers())
        assert "tickers" in result
        returned_symbols = {t["symbol"] for t in result["tickers"]}
        assert returned_symbols == set(_DEFAULT_SYMBOLS)

    def test_empty_cache_all_stale(self):
        api = _StubAPI()
        result = json.loads(api.get_live_tickers())
        for t in result["tickers"]:
            assert t["stale"] is True
            assert t["price"] is None

    def test_fresh_entry_not_stale(self):
        api = _StubAPI()
        _inject(api, "BTCUSDT", "93420.0", "0.0099")
        result = json.loads(api.get_live_tickers())
        btc = next(t for t in result["tickers"] if t["symbol"] == "BTCUSDT")
        assert btc["stale"] is False
        assert btc["price"] == "93420.0"
        assert btc["change_pct"] == "0.0099"

    def test_old_entry_is_stale(self):
        api = _StubAPI()
        old_ts = int(time.time() * 1000) - _STALE_THRESHOLD_MS - 1000
        _inject(api, "BTCUSDT", "93420.0", "0.0099", ts=old_ts)
        result = json.loads(api.get_live_tickers())
        btc = next(t for t in result["tickers"] if t["symbol"] == "BTCUSDT")
        assert btc["stale"] is True

    def test_positive_change(self):
        api = _StubAPI()
        _inject(api, "ETHUSDT", "3841.5", "0.0120")
        result = json.loads(api.get_live_tickers())
        eth = next(t for t in result["tickers"] if t["symbol"] == "ETHUSDT")
        assert float(eth["change_pct"]) > 0

    def test_negative_change(self):
        api = _StubAPI()
        _inject(api, "ETHUSDT", "3800.0", "-0.0104")
        result = json.loads(api.get_live_tickers())
        eth = next(t for t in result["tickers"] if t["symbol"] == "ETHUSDT")
        assert float(eth["change_pct"]) < 0

    def test_order_matches_symbols_list(self):
        api = _StubAPI()
        result = json.loads(api.get_live_tickers())
        symbols_in_order = [t["symbol"] for t in result["tickers"]]
        assert symbols_in_order == api._ticker_symbols

    def test_unknown_symbol_not_in_result(self):
        """Symbols not in the watch list are not returned."""
        api = _StubAPI()
        _inject(api, "WEIRDUSDT", "1.23", "0.0")  # not in _DEFAULT_SYMBOLS
        result = json.loads(api.get_live_tickers())
        returned = {t["symbol"] for t in result["tickers"]}
        assert "WEIRDUSDT" not in returned


class TestHandleTickerMsg:
    def test_snapshot_message_populates_cache(self):
        api = _StubAPI()
        msg = json.dumps({
            "topic": "tickers.BTCUSDT",
            "type": "snapshot",
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "93500.00",
                "price24hPcnt": "0.0120",
                "highPrice24h": "94000.00",
                "lowPrice24h": "92000.00",
                "volume24h": "15000.0",
            },
        })
        api._handle_ticker_msg(msg)
        with api._ticker_lock:
            entry = api._ticker_cache.get("BTCUSDT")
        assert entry is not None
        assert entry["price"] == "93500.00"
        assert entry["change_pct"] == "0.0120"

    def test_delta_message_merges_partial_fields(self):
        api = _StubAPI()
        # First inject a full entry
        _inject(api, "SOLUSDT", "180.0", "0.0300")
        # Delta only updates price
        delta = json.dumps({
            "topic": "tickers.SOLUSDT",
            "type": "delta",
            "data": {"symbol": "SOLUSDT", "lastPrice": "182.5"},
        })
        api._handle_ticker_msg(delta)
        with api._ticker_lock:
            entry = api._ticker_cache["SOLUSDT"]
        assert entry["price"] == "182.5"
        assert entry["change_pct"] == "0.0300"  # preserved from original

    def test_non_ticker_topic_ignored(self):
        api = _StubAPI()
        msg = json.dumps({"topic": "orderbook.50.BTCUSDT", "data": {"s": "BTCUSDT"}})
        api._handle_ticker_msg(msg)
        assert "BTCUSDT" not in api._ticker_cache

    def test_malformed_json_does_not_raise(self):
        api = _StubAPI()
        api._handle_ticker_msg("NOT_JSON{{{")

    def test_missing_symbol_skipped(self):
        api = _StubAPI()
        msg = json.dumps({"topic": "tickers.BTCUSDT", "data": {"lastPrice": "93000"}})
        api._handle_ticker_msg(msg)
        # symbol field is missing in data, nothing stored
        assert "BTCUSDT" not in api._ticker_cache
