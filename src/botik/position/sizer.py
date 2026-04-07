"""
PositionSizer — расчёт размера позиции, SL и TP.

Три метода расчёта qty:
  1. risk_qty    — фиксированный % от баланса на риск (всегда доступен)
  2. kelly_qty   — Kelly Criterion (только когда модель обучена, is_trained=True)
  3. fixed_qty   — фиксированный размер из конфига (fallback)

SL/TP расчёт:
  - ATR-based: SL = entry ± atr_sl_mult * ATR(14)
                TP = entry ± atr_tp_mult * ATR(14)
  - Минимальный R:R = 1:1.5 (всегда проверяется)
"""
from __future__ import annotations

import logging
from typing import Sequence

log = logging.getLogger("botik.position.sizer")

# Дефолтные множители ATR
DEFAULT_ATR_SL_MULT = 1.5
DEFAULT_ATR_TP_MULT = 2.5
DEFAULT_RISK_PCT = 0.01       # 1% от баланса на сделку
MIN_RR_RATIO = 1.5            # минимальный Risk:Reward


def calc_atr(highs: Sequence[float], lows: Sequence[float],
             closes: Sequence[float], period: int = 14) -> float:
    """Average True Range за последние period свечей."""
    if len(highs) < period + 1:
        return 0.0
    true_ranges: list[float] = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(hl, hc, lc))
    recent = true_ranges[-period:]
    return sum(recent) / len(recent) if recent else 0.0


class PositionSizer:
    """
    Рассчитывает qty, SL, TP для одной сделки.

    Параметры:
      risk_pct         — доля баланса под риск на сделку (default 1%)
      atr_sl_mult      — множитель ATR для SL (default 1.5)
      atr_tp_mult      — множитель ATR для TP (default 2.5)
      max_position_pct — максимальная доля баланса в одной позиции (default 20%)
    """

    def __init__(
        self,
        risk_pct: float = DEFAULT_RISK_PCT,
        atr_sl_mult: float = DEFAULT_ATR_SL_MULT,
        atr_tp_mult: float = DEFAULT_ATR_TP_MULT,
        max_position_pct: float = 0.20,
    ) -> None:
        self.risk_pct = risk_pct
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.max_position_pct = max_position_pct

    # ── SL / TP ───────────────────────────────────────────────

    def calc_sl_tp(
        self,
        entry: float,
        atr: float,
        direction: str,         # 'long' | 'short'
        sl_mult: float | None = None,
        tp_mult: float | None = None,
    ) -> tuple[float, float]:
        """
        Возвращает (stop_loss, take_profit) на основе ATR.
        Гарантирует минимальный R:R = MIN_RR_RATIO.
        """
        sm = sl_mult if sl_mult is not None else self.atr_sl_mult
        tm = tp_mult if tp_mult is not None else self.atr_tp_mult

        # Обеспечиваем минимальный R:R
        if tm / sm < MIN_RR_RATIO:
            tm = sm * MIN_RR_RATIO

        if direction == "long":
            sl = entry - sm * atr
            tp = entry + tm * atr
        else:
            sl = entry + sm * atr
            tp = entry - tm * atr

        return round(sl, 8), round(tp, 8)

    # ── Qty ───────────────────────────────────────────────────

    def risk_qty(self, balance: float, entry: float, stop_loss: float) -> float:
        """
        Размер позиции через фиксированный % риска.

        qty = (balance * risk_pct) / |entry - stop_loss|

        Ограничено max_position_pct * balance / entry.
        """
        stop_distance = abs(entry - stop_loss)
        if stop_distance == 0 or entry == 0:
            return 0.0

        risk_amount = balance * self.risk_pct
        qty = risk_amount / stop_distance

        # Ограничение на максимальный размер позиции
        max_qty = (balance * self.max_position_pct) / entry
        qty = min(qty, max_qty)

        return round(qty, 8)

    def kelly_qty(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        kelly_fraction: float = 0.25,   # дробный Kelly (25% — консервативно)
    ) -> float:
        """
        Kelly Criterion — оптимальный размер когда модель обучена.

        full_kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss)
        qty = balance * full_kelly * kelly_fraction / entry

        kelly_fraction=0.25 — консервативный подход (четверть Kelly).
        Используется только когда is_trained=True и win_rate > 0.5.
        """
        if avg_loss == 0 or win_rate <= 0:
            return self.risk_qty(balance, entry, stop_loss)

        rr = avg_win / avg_loss
        full_kelly = win_rate - (1 - win_rate) / rr

        if full_kelly <= 0:
            log.debug("Kelly отрицательный (%.3f) — возвращаем risk_qty", full_kelly)
            return self.risk_qty(balance, entry, stop_loss)

        fractional = full_kelly * kelly_fraction
        qty = (balance * fractional) / entry

        # Не превышаем max_position_pct
        max_qty = (balance * self.max_position_pct) / entry
        qty = min(qty, max_qty)

        return round(qty, 8)

    def calc_qty(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        *,
        is_trained: bool = False,
        win_rate: float = 0.0,
        avg_win: float = 0.0,
        avg_loss: float = 0.0,
    ) -> float:
        """
        Единая точка входа: выбирает Kelly если модель обучена, иначе risk_qty.
        """
        if is_trained and win_rate > 0.50 and avg_win > 0 and avg_loss > 0:
            return self.kelly_qty(balance, entry, stop_loss, win_rate, avg_win, avg_loss)
        return self.risk_qty(balance, entry, stop_loss)
