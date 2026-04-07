"""
Тесты модуля бэктестинга src/botik/backtest/.

Покрывают:
  - BacktestResult: to_dict(), нулевые сделки
  - FuturesBacktestRunner: нет данных, 1 свеча, 100+ свечей
  - SpotBacktestRunner: 100+ свечей
  - Метрики: profit_factor без убытков, max_drawdown
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.botik.backtest.backtest_result import BacktestResult
from src.botik.backtest.backtest_runner import (
    FuturesBacktestRunner,
    SpotBacktestRunner,
    _calc_max_drawdown,
    _calc_profit_factor,
    _calc_sharpe,
)
from src.botik.storage.db import reset_db
from src.botik.storage.migrations import run_migrations


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> str:
    """Создаёт временную SQLite БД с миграциями. Возвращает DB_URL."""
    db_path = tmp_path / "test_backtest.db"
    url = f"sqlite:///{db_path}"
    db = reset_db(url)
    with db.connect() as conn:
        run_migrations(conn)
    return url


def _insert_candles(
    db_url: str,
    symbol: str,
    category: str,
    interval: str,
    n: int = 100,
    base_price: float = 50000.0,
    spike_at: int | None = None,
) -> None:
    """
    Вставляет N свечей в price_history.
    spike_at — индекс свечи, где делаем падение (для теста спайка вниз → long вход).
    """
    db = reset_db(db_url)
    now_ms = int(time.time() * 1000)
    candle_ms = 60_000  # 1 минута

    rows = []
    price = base_price
    for i in range(n):
        ts = now_ms - (n - i) * candle_ms
        # Небольшой дрейф
        price = price * (1 + (0.0001 if i % 2 == 0 else -0.00005))

        if spike_at is not None and i == spike_at:
            # Спайк вниз: цена падает на 1% → вход long на следующей свече
            price = price * 0.990

        open_p = price * 0.9998
        high_p = price * 1.002
        low_p  = price * 0.998
        close_p = price
        volume = 10.0 + i * 0.1

        rows.append((symbol, category, interval, ts, open_p, high_p, low_p, close_p, volume))

    with db.connect() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO price_history
              (symbol, category, interval, open_time_ms,
               open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _make_futures_runner(db_url: str, **kwargs) -> FuturesBacktestRunner:
    return FuturesBacktestRunner(
        "BTCUSDT",
        interval="1",
        days_back=365,   # берём все свечи (тесты вставляют за прошлые периоды)
        balance=10_000.0,
        db_url=db_url,
        **kwargs,
    )


def _make_spot_runner(db_url: str, **kwargs) -> SpotBacktestRunner:
    return SpotBacktestRunner(
        "ETHUSDT",
        interval="1",
        days_back=365,
        balance=10_000.0,
        db_url=db_url,
        **kwargs,
    )


# ── Тест 1: BacktestResult.to_dict() ─────────────────────────────────────────

def test_backtest_result_to_dict() -> None:
    """to_dict() должен возвращать все ожидаемые ключи с корректными типами."""
    result = BacktestResult(
        symbol="BTCUSDT",
        scope="futures",
        interval="1",
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-02-01T00:00:00Z",
        total_candles=1440,
        trades=10,
        wins=7,
        losses=3,
        win_rate=70.0,
        total_pnl=350.0,
        max_drawdown=120.5,
        max_drawdown_pct=1.205,
        sharpe_ratio=1.5,
        avg_win=80.0,
        avg_loss=-40.0,
        profit_factor=4.67,
        trades_list=[],
    )

    d = result.to_dict()

    assert d["symbol"] == "BTCUSDT"
    assert d["scope"] == "futures"
    assert d["interval"] == "1"
    assert d["start_date"] == "2026-01-01T00:00:00Z"
    assert d["end_date"] == "2026-02-01T00:00:00Z"
    assert d["total_candles"] == 1440
    assert d["trades"] == 10
    assert d["wins"] == 7
    assert d["losses"] == 3
    assert abs(d["win_rate"] - 70.0) < 0.01
    assert abs(d["total_pnl"] - 350.0) < 0.01
    assert abs(d["max_drawdown"] - 120.5) < 0.01
    assert abs(d["sharpe_ratio"] - 1.5) < 0.01
    assert d["profit_factor"] == 4.67
    assert isinstance(d["trades_list"], list)


# ── Тест 2: BacktestResult с нулевыми сделками ───────────────────────────────

def test_backtest_result_win_rate_zero_trades() -> None:
    """Нулевые сделки не должны вызывать деление на ноль."""
    result = BacktestResult(
        symbol="BTCUSDT",
        scope="futures",
        interval="1",
        start_date="",
        end_date="",
        total_candles=0,
        trades=0,
        wins=0,
        losses=0,
        win_rate=0.0,
        total_pnl=0.0,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        sharpe_ratio=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        profit_factor=0.0,
    )

    d = result.to_dict()
    assert d["trades"] == 0
    assert d["win_rate"] == 0.0
    assert d["profit_factor"] == 0.0


# ── Тест 3: FuturesBacktestRunner с пустой price_history ─────────────────────

def test_futures_backtest_runner_no_data(tmp_path: Path) -> None:
    """Пустая price_history → result с 0 trades, не падает."""
    db_url = _make_db(tmp_path)
    runner = _make_futures_runner(db_url)
    result = runner.run()

    assert isinstance(result, BacktestResult)
    assert result.trades == 0
    assert result.total_candles == 0
    assert result.scope == "futures"
    assert result.symbol == "BTCUSDT"


# ── Тест 4: FuturesBacktestRunner с одной свечой ─────────────────────────────

def test_futures_backtest_runner_single_candle(tmp_path: Path) -> None:
    """1 свеча → 0 trades (недостаточно данных для ATR и детекции спайка)."""
    db_url = _make_db(tmp_path)
    _insert_candles(db_url, "BTCUSDT", "linear", "1", n=1)

    runner = _make_futures_runner(db_url)
    result = runner.run()

    assert isinstance(result, BacktestResult)
    assert result.trades == 0
    assert result.total_candles == 1


# ── Тест 5: FuturesBacktestRunner базовый прогон (100+ свечей) ───────────────

def test_futures_backtest_basic(tmp_path: Path) -> None:
    """100+ свечей со спайком → runner не падает, возвращает BacktestResult."""
    db_url = _make_db(tmp_path)
    # Вставляем 150 свечей, спайк вниз на свече 50 → вход long
    _insert_candles(
        db_url, "BTCUSDT", "linear", "1",
        n=150, base_price=50000.0, spike_at=50,
    )

    runner = _make_futures_runner(
        db_url,
        spike_bps=20.0,   # низкий порог для гарантированного входа
        risk_pct=0.01,
    )
    result = runner.run()

    assert isinstance(result, BacktestResult)
    assert result.total_candles == 150
    assert result.scope == "futures"
    assert result.symbol == "BTCUSDT"
    # Метрики не должны быть NaN/Inf кроме profit_factor
    assert not math.isnan(result.total_pnl)
    assert not math.isnan(result.win_rate)
    assert not math.isnan(result.sharpe_ratio)
    assert not math.isnan(result.max_drawdown)
    # trades_list — список словарей
    assert isinstance(result.trades_list, list)


# ── Тест 6: SpotBacktestRunner базовый прогон ────────────────────────────────

def test_spot_backtest_basic(tmp_path: Path) -> None:
    """100+ свечей для спота → runner не падает, возвращает BacktestResult."""
    db_url = _make_db(tmp_path)
    _insert_candles(
        db_url, "ETHUSDT", "spot", "1",
        n=150, base_price=3000.0, spike_at=50,
    )

    runner = _make_spot_runner(
        db_url,
        spike_bps=20.0,
        risk_pct=0.01,
    )
    result = runner.run()

    assert isinstance(result, BacktestResult)
    assert result.total_candles == 150
    assert result.scope == "spot"
    assert result.symbol == "ETHUSDT"
    assert not math.isnan(result.total_pnl)
    assert isinstance(result.trades_list, list)


# ── Тест 7: profit_factor без убытков = inf ───────────────────────────────────

def test_backtest_profit_factor_no_losses() -> None:
    """Если все сделки прибыльны, profit_factor должен быть inf."""
    win_pnls = [100.0, 50.0, 75.0]
    loss_pnls: list[float] = []

    pf = _calc_profit_factor(win_pnls, loss_pnls)
    assert pf == float("inf")

    # to_dict преобразует inf в строку "inf"
    result = BacktestResult(
        symbol="TEST",
        scope="futures",
        interval="1",
        start_date="",
        end_date="",
        total_candles=10,
        trades=3,
        wins=3,
        losses=0,
        win_rate=100.0,
        total_pnl=225.0,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        sharpe_ratio=1.0,
        avg_win=75.0,
        avg_loss=0.0,
        profit_factor=float("inf"),
    )

    d = result.to_dict()
    assert d["profit_factor"] == "inf"


# ── Тест 8: max_drawdown > 0 при падении equity ───────────────────────────────

def test_backtest_max_drawdown() -> None:
    """Если equity падает, drawdown должен быть > 0."""
    # Equity curve: растём, потом падаем
    equity = [10000.0, 10500.0, 11000.0, 10200.0, 9800.0, 10100.0]
    max_dd, max_dd_pct = _calc_max_drawdown(equity)

    assert max_dd > 0
    # Максимальная просадка: пик 11000 → минимум 9800 = 1200
    assert abs(max_dd - 1200.0) < 1e-6
    assert max_dd_pct > 0
    # % от начального (10000): 1200/10000*100 = 12%
    assert abs(max_dd_pct - 12.0) < 1e-4


# ── Дополнительные тесты вспомогательных функций ─────────────────────────────

def test_calc_sharpe_too_few_trades() -> None:
    """Меньше 5 сделок → sharpe == 0."""
    assert _calc_sharpe([10.0, 20.0, 30.0]) == 0.0
    assert _calc_sharpe([]) == 0.0


def test_calc_sharpe_stable_returns() -> None:
    """Стабильные одинаковые возвраты → std=0 → sharpe=0."""
    assert _calc_sharpe([10.0, 10.0, 10.0, 10.0, 10.0, 10.0]) == 0.0


def test_calc_profit_factor_no_wins() -> None:
    """Если нет побед, profit_factor = 0."""
    pf = _calc_profit_factor([], [-100.0, -50.0])
    assert pf == 0.0


def test_futures_runner_scope_and_category(tmp_path: Path) -> None:
    """scope='futures', category='linear' у FuturesBacktestRunner."""
    db_url = _make_db(tmp_path)
    runner = FuturesBacktestRunner("BTCUSDT", "1", db_url=db_url)
    assert runner.scope == "futures"
    assert runner.category == "linear"


def test_spot_runner_scope_and_category(tmp_path: Path) -> None:
    """scope='spot', category='spot' у SpotBacktestRunner."""
    db_url = _make_db(tmp_path)
    runner = SpotBacktestRunner("ETHUSDT", "1", db_url=db_url)
    assert runner.scope == "spot"
    assert runner.category == "spot"
