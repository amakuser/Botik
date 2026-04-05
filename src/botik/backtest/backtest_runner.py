"""
BacktestRunner — симуляция торгового цикла на исторических свечах.

Архитектура:
  _BaseBacktestRunner — общая логика: загрузка свечей, детекция спайка,
                        вычисление метрик (drawdown, Sharpe, profit factor).
  FuturesBacktestRunner — использует FuturesPaperEngine, category='linear'
  SpotBacktestRunner    — использует SpotPaperEngine, category='spot'

Упрощения для бэктеста (vs live):
  - Нет реального orderbook — используем OHLCV
  - Вход: спайк close[-1] vs close[-5] (>= spike_bps порог)
  - Imbalance заменён константой (0.65 для futures, 0.67 для spot)
  - Цена входа = close свечи (worst-case приближение)
  - engine.on_price_tick() вызывается на каждой свече для проверки выхода

Параметры по умолчанию берутся из env vars (те же что в live runner-ах).
Можно переопределить через kwargs при создании класса.

Пример:
    runner = FuturesBacktestRunner("BTCUSDT", "1", days_back=30, balance=10000)
    result = runner.run()
    print(result.to_dict())
"""
from __future__ import annotations

import logging
import math
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.botik.backtest.backtest_result import BacktestResult
from src.botik.position.sizer import PositionSizer, calc_atr
from src.botik.storage.db import get_db

log = logging.getLogger("botik.backtest.runner")

# ── Минимальный буфер свечей для надёжного расчёта ATR и спайка ──
_MIN_CANDLES_FOR_TRADE = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_to_iso(ts_ms: int) -> str:
    """Конвертирует unix-ms в ISO строку."""
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _calc_max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    """
    Считает максимальную просадку по equity curve.

    Возвращает (abs_drawdown, pct_drawdown_from_initial).
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    initial = equity_curve[0] if equity_curve[0] != 0 else 1.0

    for val in equity_curve:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd

    return max_dd, (max_dd / abs(initial) * 100) if initial else 0.0


def _calc_sharpe(pnl_series: list[float]) -> float:
    """
    Коэффициент Шарпа: (mean_return / std_return) * sqrt(252).
    Если сделок < 5 или std == 0 — возвращает 0.
    """
    if len(pnl_series) < 5:
        return 0.0
    n = len(pnl_series)
    mean = sum(pnl_series) / n
    variance = sum((x - mean) ** 2 for x in pnl_series) / n
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    return (mean / std) * math.sqrt(252)


def _calc_profit_factor(win_pnls: list[float], loss_pnls: list[float]) -> float:
    """
    Profit Factor = sum(win_pnl) / abs(sum(loss_pnl)).
    Возвращает float('inf') если нет убытков, 0.0 если нет побед.
    """
    total_wins = sum(win_pnls) if win_pnls else 0.0
    total_losses = sum(loss_pnls) if loss_pnls else 0.0

    if total_losses == 0:
        return float("inf") if total_wins > 0 else 0.0

    abs_losses = abs(total_losses)
    if abs_losses == 0:
        return float("inf")

    return total_wins / abs_losses


class _BaseBacktestRunner(ABC):
    """
    Базовый класс бэктест-раннера.

    Читает свечи из price_history, симулирует торговый цикл,
    собирает статистику, возвращает BacktestResult.

    Параметры:
      symbol       — торговый инструмент
      interval     — таймфрейм ("1", "5", "15", "60")
      days_back    — кол-во дней назад для загрузки данных
      balance      — начальный виртуальный баланс (USDT)
      **kwargs     — переопределение стратегических параметров:
                       risk_pct, atr_sl_mult, atr_tp_mult, max_pos_pct,
                       spike_bps, hold_timeout_h
    """

    def __init__(
        self,
        symbol: str,
        interval: str,
        days_back: int = 30,
        balance: float | None = None,
        *,
        risk_pct: float | None = None,
        atr_sl_mult: float | None = None,
        atr_tp_mult: float | None = None,
        max_pos_pct: float | None = None,
        spike_bps: float | None = None,
        hold_timeout_h: float | None = None,
        db_url: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.interval = interval
        self.days_back = days_back
        self._db_url = db_url

        # Параметры — из kwargs, затем из env vars, затем дефолты
        self.balance = balance if balance is not None else float(
            os.environ.get("FUTURES_BALANCE", "10000")
        )
        self.risk_pct = risk_pct if risk_pct is not None else (
            float(os.environ.get("FUTURES_RISK_PCT", "1.0")) / 100
        )
        self.atr_sl_mult = atr_sl_mult if atr_sl_mult is not None else float(
            os.environ.get("FUTURES_ATR_SL_MULT", "1.5")
        )
        self.atr_tp_mult = atr_tp_mult if atr_tp_mult is not None else float(
            os.environ.get("FUTURES_ATR_TP_MULT", "2.5")
        )
        self.max_pos_pct = max_pos_pct if max_pos_pct is not None else (
            float(os.environ.get("FUTURES_MAX_POS_PCT", "15")) / 100
        )
        self.spike_bps = spike_bps if spike_bps is not None else float(
            os.environ.get("FUTURES_SPIKE_BPS", "80")
        )
        self.hold_timeout_h = hold_timeout_h if hold_timeout_h is not None else float(
            os.environ.get("FUTURES_HOLD_TIMEOUT_H", "4")
        )

        self.sizer = PositionSizer(
            risk_pct=self.risk_pct,
            atr_sl_mult=self.atr_sl_mult,
            atr_tp_mult=self.atr_tp_mult,
            max_position_pct=self.max_pos_pct,
        )

    # ── Абстрактные методы (реализуются в наследниках) ────────────

    @property
    @abstractmethod
    def scope(self) -> str:
        """'futures' | 'spot'"""

    @property
    @abstractmethod
    def category(self) -> str:
        """'linear' | 'spot' — используется в WHERE clause price_history"""

    @property
    @abstractmethod
    def imbalance_threshold(self) -> float:
        """Порог imbalance для открытия позиции (константа для бэктеста)"""

    @abstractmethod
    def _open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        stop_loss: float,
        take_profit: float,
        open_time: str,
    ) -> dict[str, Any] | None:
        """Открывает сделку. Возвращает dict или None если нельзя открыть."""

    @abstractmethod
    def _tick(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """Обрабатывает один тик цены. Возвращает список закрытых сделок."""

    @abstractmethod
    def _has_open_position(self, symbol: str) -> bool:
        """Проверяет наличие открытой позиции."""

    # ── Основной метод ────────────────────────────────────────────

    def run(self) -> BacktestResult:
        """
        Запускает бэктест. Возвращает BacktestResult.
        """
        candles = self._load_candles()

        if not candles:
            return self._empty_result(total_candles=0)

        total_candles = len(candles)
        start_date = _ms_to_iso(int(candles[0][0]))
        end_date = _ms_to_iso(int(candles[-1][0]))

        # Equity curve и список закрытых сделок
        equity = self.balance
        equity_curve: list[float] = [equity]
        closed_trades: list[dict[str, Any]] = []

        # Буфер OHLCV для ATR и детекции спайка
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []

        for row in candles:
            open_time_ms, o, h, lo, c, vol = (
                int(row[0]), float(row[1]), float(row[2]),
                float(row[3]), float(row[4]), float(row[5]),
            )

            # Накапливаем буфер
            highs.append(h)
            lows.append(lo)
            closes.append(c)

            # Проверяем выход из открытых позиций
            closed_now = self._tick(self.symbol, c)
            for trade in closed_now:
                pnl = float(trade.get("net_pnl", 0.0))
                equity += pnl
                equity_curve.append(equity)
                closed_trades.append({
                    "open_time": trade.get("open_time", ""),
                    "close_time": _utc_now(),
                    "side": trade.get("side", ""),
                    "entry": float(trade.get("entry_price", 0.0)),
                    "exit": float(trade.get("exit_price", c)),
                    "pnl": round(pnl, 4),
                    "reason": trade.get("exit_reason", ""),
                })

            # Попытка открыть новую позицию (если нет открытой)
            if len(closes) < _MIN_CANDLES_FOR_TRADE:
                continue

            if self._has_open_position(self.symbol):
                continue

            # ATR
            atr = calc_atr(
                highs[-50:], lows[-50:], closes[-50:], period=14
            )
            if atr <= 0:
                continue

            # Детекция спайка: close vs close[-5]
            if len(closes) < 5:
                continue
            ref_price = closes[-6] if len(closes) >= 6 else closes[0]
            if ref_price <= 0:
                continue
            spike_bps = (c - ref_price) / ref_price * 10_000

            # Сигнал входа (imbalance = константа для бэктеста)
            threshold = self.spike_bps
            imb = self.imbalance_threshold

            if spike_bps < -threshold and imb > 0.5:
                side = "long"
            elif spike_bps > threshold and imb < 0.5:
                side = "short"
            else:
                continue

            entry_price = c  # worst case approximation
            sl, tp = self.sizer.calc_sl_tp(entry_price, atr, side)
            qty = self.sizer.calc_qty(equity, entry_price, sl)

            if qty <= 0:
                continue

            open_time_iso = _ms_to_iso(open_time_ms)
            self._open_trade(
                symbol=self.symbol,
                side=side,
                entry_price=entry_price,
                qty=qty,
                stop_loss=sl,
                take_profit=tp,
                open_time=open_time_iso,
            )

        # Считаем метрики
        return self._build_result(
            total_candles=total_candles,
            start_date=start_date,
            end_date=end_date,
            closed_trades=closed_trades,
            equity_curve=equity_curve,
        )

    # ── Загрузка данных ──────────────────────────────────────────

    def _load_candles(self) -> list[tuple]:
        """
        Загружает свечи из price_history.
        Возвращает список кортежей: (open_time_ms, open, high, low, close, volume)
        """
        since_ms = int((time.time() - self.days_back * 86400) * 1000)
        try:
            db = get_db(self._db_url)
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT open_time_ms, open, high, low, close, volume
                    FROM price_history
                    WHERE symbol=? AND category=? AND interval=?
                      AND open_time_ms >= ?
                    ORDER BY open_time_ms ASC
                    """,
                    (self.symbol, self.category, self.interval, since_ms),
                ).fetchall()
            return [tuple(r) for r in rows]
        except Exception as exc:
            log.warning("_load_candles error: %s", exc)
            return []

    # ── Построение результата ─────────────────────────────────────

    def _build_result(
        self,
        total_candles: int,
        start_date: str,
        end_date: str,
        closed_trades: list[dict[str, Any]],
        equity_curve: list[float],
    ) -> BacktestResult:
        trades = len(closed_trades)
        win_pnls = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
        loss_pnls = [t["pnl"] for t in closed_trades if t["pnl"] <= 0]

        wins = len(win_pnls)
        losses = len(loss_pnls)
        win_rate = (wins / trades * 100) if trades > 0 else 0.0
        total_pnl = sum(t["pnl"] for t in closed_trades)

        avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
        avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0

        profit_factor = _calc_profit_factor(win_pnls, loss_pnls)

        max_dd, max_dd_pct = _calc_max_drawdown(equity_curve)

        pnl_series = [t["pnl"] for t in closed_trades]
        sharpe = _calc_sharpe(pnl_series)

        return BacktestResult(
            symbol=self.symbol,
            scope=self.scope,
            interval=self.interval,
            start_date=start_date,
            end_date=end_date,
            total_candles=total_candles,
            trades=trades,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 2),
            total_pnl=round(total_pnl, 4),
            max_drawdown=round(max_dd, 4),
            max_drawdown_pct=round(max_dd_pct, 4),
            sharpe_ratio=round(sharpe, 4),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            profit_factor=profit_factor,
            trades_list=closed_trades,
        )

    def _empty_result(self, total_candles: int = 0) -> BacktestResult:
        """Возвращает пустой результат (нет данных)."""
        return BacktestResult(
            symbol=self.symbol,
            scope=self.scope,
            interval=self.interval,
            start_date="",
            end_date="",
            total_candles=total_candles,
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
            trades_list=[],
        )


# ─────────────────────────────────────────────────────────────────────────────
#  FuturesBacktestRunner
# ─────────────────────────────────────────────────────────────────────────────

class FuturesBacktestRunner(_BaseBacktestRunner):
    """
    Бэктест для фьючерсной стратегии.

    Симулирует open/close позиций через упрощённый in-memory движок
    (не пишет в БД — бэктест изолирован от live данных).
    """

    FUTURES_IMBALANCE_THRESHOLD = 0.65   # константа для бэктеста

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # In-memory состояние позиций (изолировано от БД)
        self._open_position: dict[str, Any] | None = None

    @property
    def scope(self) -> str:
        return "futures"

    @property
    def category(self) -> str:
        return "linear"

    @property
    def imbalance_threshold(self) -> float:
        return self.FUTURES_IMBALANCE_THRESHOLD

    def _open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        stop_loss: float,
        take_profit: float,
        open_time: str,
    ) -> dict[str, Any] | None:
        """Открывает позицию в памяти (без БД)."""
        if self._open_position is not None:
            return None

        self._open_position = {
            "trade_id": f"bt-{uuid.uuid4().hex[:8]}",
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "qty": qty,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "open_time": open_time,
        }
        return self._open_position

    def _tick(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """Проверяет SL/TP для открытой позиции."""
        pos = self._open_position
        if pos is None or pos["symbol"] != symbol:
            return []

        side = pos["side"]
        sl = pos["stop_loss"]
        tp = pos["take_profit"]
        entry = pos["entry_price"]
        qty = pos["qty"]

        should_close = False
        reason = ""

        if side == "long":
            if price <= sl:
                should_close, reason = True, "sl_hit"
            elif price >= tp:
                should_close, reason = True, "tp_hit"
        else:  # short
            if price >= sl:
                should_close, reason = True, "sl_hit"
            elif price <= tp:
                should_close, reason = True, "tp_hit"

        if not should_close:
            return []

        # Рассчитываем PnL (фьючерсы, комиссия 0.055% taker)
        if side == "long":
            gross_pnl = (price - entry) * qty
        else:
            gross_pnl = (entry - price) * qty

        fee = price * qty * 0.00055
        net_pnl = gross_pnl - fee

        result = {
            "trade_id": pos["trade_id"],
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": price,
            "qty": qty,
            "net_pnl": net_pnl,
            "exit_reason": reason,
            "open_time": pos["open_time"],
        }
        self._open_position = None
        return [result]

    def _has_open_position(self, symbol: str) -> bool:
        return (
            self._open_position is not None
            and self._open_position.get("symbol") == symbol
        )


# ─────────────────────────────────────────────────────────────────────────────
#  SpotBacktestRunner
# ─────────────────────────────────────────────────────────────────────────────

class SpotBacktestRunner(_BaseBacktestRunner):
    """
    Бэктест для спотовой стратегии.

    Только long (покупка/продажа). Нет коротких позиций.
    Комиссия: 0.1% taker (Bybit spot).
    """

    SPOT_IMBALANCE_THRESHOLD = 0.67   # константа для бэктеста

    def __init__(self, *args, **kwargs) -> None:
        # Spot использует другие env vars по умолчанию
        if "spike_bps" not in kwargs:
            kwargs["spike_bps"] = float(os.environ.get("SPOT_SPIKE_BPS", "80"))
        if "hold_timeout_h" not in kwargs:
            kwargs["hold_timeout_h"] = float(os.environ.get("SPOT_HOLD_TIMEOUT_H", "8"))
        super().__init__(*args, **kwargs)
        # In-memory холдинг
        self._holding: dict[str, Any] | None = None

    @property
    def scope(self) -> str:
        return "spot"

    @property
    def category(self) -> str:
        return "spot"

    @property
    def imbalance_threshold(self) -> float:
        return self.SPOT_IMBALANCE_THRESHOLD

    def _open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        stop_loss: float,
        take_profit: float,
        open_time: str,
    ) -> dict[str, Any] | None:
        """Открывает long спот позицию в памяти (только buy)."""
        if self._holding is not None:
            return None
        if side != "long":
            return None   # spot — только long

        # Стоимость входа с учётом комиссии
        cost = entry_price * qty
        fee = cost * 0.001   # 0.1% taker

        self._holding = {
            "trade_id": f"bt-{uuid.uuid4().hex[:8]}",
            "symbol": symbol,
            "side": "long",
            "entry_price": entry_price,
            "qty": qty,
            "entry_fee": fee,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "open_time": open_time,
        }
        return self._holding

    def _tick(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """Проверяет SL/TP для открытого холдинга."""
        pos = self._holding
        if pos is None or pos["symbol"] != symbol:
            return []

        sl = pos["stop_loss"]
        tp = pos["take_profit"]
        entry = pos["entry_price"]
        qty = pos["qty"]
        entry_fee = pos["entry_fee"]

        should_close = False
        reason = ""

        if price <= sl:
            should_close, reason = True, "sl_hit"
        elif price >= tp:
            should_close, reason = True, "tp_hit"

        if not should_close:
            return []

        # PnL (spot): gross - sell_fee - cost_basis
        gross = price * qty
        sell_fee = gross * 0.001
        net_proceeds = gross - sell_fee
        cost_basis = entry * qty + entry_fee
        net_pnl = net_proceeds - cost_basis

        result = {
            "trade_id": pos["trade_id"],
            "symbol": symbol,
            "side": "long",
            "entry_price": entry,
            "exit_price": price,
            "qty": qty,
            "net_pnl": net_pnl,
            "exit_reason": reason,
            "open_time": pos["open_time"],
        }
        self._holding = None
        return [result]

    def _has_open_position(self, symbol: str) -> bool:
        return (
            self._holding is not None
            and self._holding.get("symbol") == symbol
        )
