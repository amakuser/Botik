"""
Tests for AnalyticsMixin (Task #30: PnL analytics).

Covers:
- _calc_max_drawdown: correct drawdown from various series
- _build_equity_curve: daily bucketing, cumulative sum
- _compute_analytics: win_rate, avg_pnl, best/worst, today_pnl, by_scope, recent_trades
- _build_by_scope: per-scope aggregation
- _build_recent_trades: reversal, limit
- get_pnl_analytics: returns empty JSON when no tables; returns data from DB
- _collect_trades: reads from futures_paper_trades and outcomes, applies filters
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.botik.gui.api_analytics_mixin import (
    AnalyticsMixin,
    _build_equity_curve,
    _build_recent_trades,
    _build_by_scope,
    _calc_max_drawdown,
    _compute_analytics,
    _empty_analytics,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trade(symbol="BTCUSDT", scope="futures", pnl=1.0, win=1, closed_at="2026-03-22 10:00:00"):
    return {"symbol": symbol, "scope": scope, "pnl": pnl, "win": win, "closed_at": closed_at}


def _make_db() -> sqlite3.Connection:
    """In-memory SQLite with futures_paper_trades and outcomes tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE futures_paper_trades (
            id INTEGER PRIMARY KEY, symbol TEXT, model_scope TEXT,
            net_pnl REAL, was_profitable INTEGER,
            opened_at_utc TEXT, closed_at_utc TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE outcomes (
            signal_id TEXT PRIMARY KEY, symbol TEXT, model_scope TEXT,
            net_pnl_quote REAL, was_profitable INTEGER, closed_at_utc TEXT
        )
    """)
    conn.commit()
    return conn


# ── _calc_max_drawdown ────────────────────────────────────────────────────────

def test_max_drawdown_empty():
    assert _calc_max_drawdown([]) == 0.0

def test_max_drawdown_all_positive():
    # monotonically increasing — no drawdown
    assert _calc_max_drawdown([1.0, 2.0, 3.0, 4.0]) == 0.0

def test_max_drawdown_single_dip():
    # peak=3, trough=1 → dd=-2
    assert _calc_max_drawdown([1.0, 3.0, 1.0]) == pytest.approx(-2.0)

def test_max_drawdown_multiple_dips():
    # peak=10, trough=4 → dd=-6
    assert _calc_max_drawdown([1.0, 10.0, 7.0, 4.0, 6.0]) == pytest.approx(-6.0)

def test_max_drawdown_all_negative():
    # no peak to fall from → should return 0
    result = _calc_max_drawdown([-3.0, -5.0, -8.0])
    assert result <= 0.0

def test_max_drawdown_single_value():
    assert _calc_max_drawdown([5.0]) == 0.0


# ── _build_equity_curve ───────────────────────────────────────────────────────

def test_equity_curve_empty():
    assert _build_equity_curve([]) == []

def test_equity_curve_single_trade():
    trades = [_make_trade(pnl=10.0, closed_at="2026-03-01 12:00:00")]
    curve  = _build_equity_curve(trades)
    assert len(curve) == 1
    assert curve[0]["date"] == "2026-03-01"
    assert curve[0]["daily_pnl"] == pytest.approx(10.0)
    assert curve[0]["cumulative_pnl"] == pytest.approx(10.0)

def test_equity_curve_cumulative():
    trades = [
        _make_trade(pnl=5.0,  closed_at="2026-03-01 10:00:00"),
        _make_trade(pnl=3.0,  closed_at="2026-03-01 15:00:00"),  # same day
        _make_trade(pnl=-2.0, closed_at="2026-03-02 10:00:00"),
    ]
    curve = _build_equity_curve(trades)
    assert len(curve) == 2
    assert curve[0]["date"] == "2026-03-01"
    assert curve[0]["daily_pnl"] == pytest.approx(8.0)
    assert curve[0]["cumulative_pnl"] == pytest.approx(8.0)
    assert curve[1]["date"] == "2026-03-02"
    assert curve[1]["daily_pnl"] == pytest.approx(-2.0)
    assert curve[1]["cumulative_pnl"] == pytest.approx(6.0)

def test_equity_curve_sorted_by_date():
    trades = [
        _make_trade(pnl=1.0, closed_at="2026-03-03 00:00:00"),
        _make_trade(pnl=2.0, closed_at="2026-03-01 00:00:00"),
    ]
    curve = _build_equity_curve(trades)
    dates = [c["date"] for c in curve]
    assert dates == sorted(dates)


# ── _build_by_scope ───────────────────────────────────────────────────────────

def test_by_scope_single():
    trades = [
        _make_trade(scope="futures", pnl=10.0, win=1),
        _make_trade(scope="futures", pnl=-2.0, win=0),
    ]
    result = _build_by_scope(trades)
    assert "futures" in result
    assert result["futures"]["trade_count"] == 2
    assert result["futures"]["total_pnl"] == pytest.approx(8.0)
    assert result["futures"]["win_rate"] == pytest.approx(0.5)
    assert result["futures"]["avg_pnl"] == pytest.approx(4.0)

def test_by_scope_multiple():
    trades = [
        _make_trade(scope="futures", pnl=5.0, win=1),
        _make_trade(scope="spot",    pnl=3.0, win=1),
    ]
    result = _build_by_scope(trades)
    assert set(result.keys()) == {"futures", "spot"}
    assert result["spot"]["total_pnl"] == pytest.approx(3.0)


# ── _build_recent_trades ──────────────────────────────────────────────────────

def test_recent_trades_reversal():
    trades = [_make_trade(pnl=float(i), closed_at=f"2026-03-{i:02d} 00:00:00") for i in range(1, 6)]
    recent = _build_recent_trades(trades, limit=3)
    # last 3 reversed → most recent first
    assert recent[0]["pnl"] == pytest.approx(5.0)
    assert recent[2]["pnl"] == pytest.approx(3.0)

def test_recent_trades_limit():
    trades = [_make_trade(pnl=1.0) for _ in range(25)]
    assert len(_build_recent_trades(trades, limit=20)) == 20

def test_recent_trades_empty():
    assert _build_recent_trades([]) == []


# ── _compute_analytics ────────────────────────────────────────────────────────

def test_compute_analytics_basic():
    trades = [
        _make_trade(pnl=10.0, win=1, closed_at="2025-01-01 10:00:00"),
        _make_trade(pnl=-4.0, win=0, closed_at="2025-01-02 10:00:00"),
        _make_trade(pnl=6.0,  win=1, closed_at="2025-01-03 10:00:00"),
    ]
    result = _compute_analytics(trades)
    assert result["trade_count"] == 3
    assert result["total_pnl"] == pytest.approx(12.0)
    assert result["win_rate"] == pytest.approx(round(2/3, 4), abs=1e-4)
    assert result["avg_pnl"] == pytest.approx(4.0)
    assert result["best_trade"] == pytest.approx(10.0)
    assert result["worst_trade"] == pytest.approx(-4.0)
    assert len(result["equity_curve"]) == 3
    assert result["max_drawdown"] <= 0.0

def test_compute_analytics_all_keys():
    trades = [_make_trade()]
    result = _compute_analytics(trades)
    required = {"total_pnl","win_rate","max_drawdown","trade_count","avg_pnl",
                "today_pnl","best_trade","worst_trade","equity_curve","by_scope","recent_trades"}
    assert required.issubset(result.keys())

def test_compute_analytics_today_pnl():
    today = date.today().isoformat()
    trades = [
        _make_trade(pnl=7.0, closed_at=f"{today} 09:00:00"),
        _make_trade(pnl=3.0, closed_at="2025-01-01 09:00:00"),  # old trade
    ]
    result = _compute_analytics(trades)
    assert result["today_pnl"] == pytest.approx(7.0)


# ── AnalyticsMixin.get_pnl_analytics ─────────────────────────────────────────

class _DummyMixin(AnalyticsMixin):
    """Minimal mixin stub that provides _db_connect / _table_exists / _table_columns."""

    def __init__(self, conn: sqlite3.Connection | None):
        self._conn = conn

    def _db_connect(self, path):
        return self._conn

    def _table_exists(self, conn, name):
        try:
            conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
            return True
        except Exception:
            return False

    def _table_columns(self, conn, name):
        cur = conn.execute(f"PRAGMA table_info({name})")
        return {row[1] for row in cur.fetchall()}


def test_get_pnl_analytics_no_db():
    api    = _DummyMixin(None)
    result = json.loads(api.get_pnl_analytics())
    assert result["trade_count"] == 0
    assert result["equity_curve"] == []


def test_get_pnl_analytics_empty_tables():
    conn = _make_db()
    api  = _DummyMixin(conn)
    with patch("src.botik.gui.api_analytics_mixin._resolve_db_path", return_value=":memory:"), \
         patch("src.botik.gui.api_analytics_mixin._load_yaml", return_value={}):
        result = json.loads(api.get_pnl_analytics())
    assert result["trade_count"] == 0


def test_get_pnl_analytics_from_futures_paper():
    conn = _make_db()
    conn.execute(
        "INSERT INTO futures_paper_trades (symbol, model_scope, net_pnl, was_profitable, "
        "opened_at_utc, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "futures", 12.5, 1, "2026-03-20 10:00:00", "2026-03-20 11:00:00"),
    )
    conn.execute(
        "INSERT INTO futures_paper_trades (symbol, model_scope, net_pnl, was_profitable, "
        "opened_at_utc, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        ("ETHUSDT", "futures", -3.0, 0, "2026-03-21 10:00:00", "2026-03-21 11:00:00"),
    )
    conn.commit()
    api = _DummyMixin(conn)
    with patch("src.botik.gui.api_analytics_mixin._resolve_db_path", return_value=":memory:"), \
         patch("src.botik.gui.api_analytics_mixin._load_yaml", return_value={}):
        result = json.loads(api.get_pnl_analytics(scope="all", days=90))
    assert result["trade_count"] == 2
    assert result["total_pnl"] == pytest.approx(9.5)
    assert result["win_rate"] == pytest.approx(0.5)
    assert "futures" in result["by_scope"]


def test_get_pnl_analytics_from_outcomes():
    conn = _make_db()
    conn.execute(
        "INSERT INTO outcomes (signal_id, symbol, model_scope, net_pnl_quote, "
        "was_profitable, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "SOLUSDT", "spot", 5.0, 1, "2026-03-22 08:00:00"),
    )
    conn.commit()
    api = _DummyMixin(conn)
    with patch("src.botik.gui.api_analytics_mixin._resolve_db_path", return_value=":memory:"), \
         patch("src.botik.gui.api_analytics_mixin._load_yaml", return_value={}):
        result = json.loads(api.get_pnl_analytics(scope="spot", days=90))
    assert result["trade_count"] == 1
    assert result["total_pnl"] == pytest.approx(5.0)
    assert "spot" in result["by_scope"]


def test_get_pnl_analytics_scope_filter():
    conn = _make_db()
    conn.execute(
        "INSERT INTO futures_paper_trades (symbol, model_scope, net_pnl, was_profitable, "
        "opened_at_utc, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "futures", 10.0, 1, "2026-03-20 10:00:00", "2026-03-20 11:00:00"),
    )
    conn.execute(
        "INSERT INTO outcomes (signal_id, symbol, model_scope, net_pnl_quote, "
        "was_profitable, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        ("s1", "ETHUSDT", "spot", 3.0, 1, "2026-03-20 12:00:00"),
    )
    conn.commit()
    api = _DummyMixin(conn)
    with patch("src.botik.gui.api_analytics_mixin._resolve_db_path", return_value=":memory:"), \
         patch("src.botik.gui.api_analytics_mixin._load_yaml", return_value={}):
        result = json.loads(api.get_pnl_analytics(scope="futures", days=90))
    # scope filter: only futures trades
    assert result["trade_count"] == 1
    assert result["total_pnl"] == pytest.approx(10.0)
