"""
OutcomeLearner — Model 3: обратная связь от результатов сделок.

Не торгует сам — корректирует параметры Predictor и PositionSizer:
  - entry_threshold (поднять если много убытков, опустить если пропускаем хорошие входы)
  - optimal_sl_mult и optimal_tp_mult на основе реальных результатов
  - win_rate и avg_win/loss для Kelly Criterion в PositionSizer

Обновляется каждые RETRAIN_EVERY_N закрытых сделок.

Использует: статистику из futures_paper_trades + существующий bandit.py
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("botik.ml.outcome_learner")

RETRAIN_EVERY_N = 50        # обновляемся каждые 50 сделок
MIN_SAMPLES = 30            # минимум сделок для первого обновления
THRESHOLD_STEP = 0.02       # шаг изменения порога входа
MAX_THRESHOLD = 0.75
MIN_THRESHOLD = 0.45
WINDOW = 200                # последние N сделок для расчёта статистики


@dataclass
class OutcomeStats:
    """Текущая статистика сделок."""
    total: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_win_usdt: float = 0.0
    avg_loss_usdt: float = 0.0
    total_pnl: float = 0.0
    avg_hold_ms: float = 0.0
    optimal_sl_mult: float = 1.5
    optimal_tp_mult: float = 2.5


class OutcomeLearner:
    """
    Адаптирует параметры системы по результатам реальных сделок.

    Взаимодействие:
      outcome_learner.record_trade(pnl, hold_ms, sl_hit, tp_hit)
      → каждые N сделок вызывает _update_params()
      → predictor.entry_threshold обновляется
      → sizer получает свежий win_rate для Kelly
    """

    def __init__(self, model_scope: str = "futures") -> None:
        self.model_scope = model_scope
        self._trades: deque[dict[str, Any]] = deque(maxlen=WINDOW)
        self._since_last_update = 0
        self.stats = OutcomeStats()

    # ── Публичный API ─────────────────────────────────────────

    def record_trade(
        self,
        net_pnl: float,
        hold_time_ms: int = 0,
        exit_reason: str = "",
        sl_mult_used: float = 1.5,
        tp_mult_used: float = 2.5,
    ) -> bool:
        """
        Записывает результат закрытой сделки.
        Возвращает True если произошло обновление параметров.
        """
        self._trades.append({
            "pnl": net_pnl,
            "hold_ms": hold_time_ms,
            "exit": exit_reason,
            "sl_mult": sl_mult_used,
            "tp_mult": tp_mult_used,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._since_last_update += 1

        if (self._since_last_update >= RETRAIN_EVERY_N
                and len(self._trades) >= MIN_SAMPLES):
            self._update_stats()
            self._since_last_update = 0
            return True
        return False

    def needs_retrain(self) -> bool:
        return self._since_last_update >= RETRAIN_EVERY_N and len(self._trades) >= MIN_SAMPLES

    def get_stats(self) -> OutcomeStats:
        """Возвращает текущую статистику (обновляет при необходимости)."""
        if len(self._trades) >= MIN_SAMPLES:
            self._update_stats()
        return self.stats

    def get_kelly_params(self) -> dict[str, float]:
        """Параметры для Kelly Criterion в PositionSizer."""
        s = self.get_stats()
        return {
            "win_rate":  s.win_rate,
            "avg_win":   s.avg_win_usdt,
            "avg_loss":  s.avg_loss_usdt,
        }

    def suggest_threshold(self, current_threshold: float) -> float:
        """
        Предлагает новый порог входа для Predictor.

        Логика:
          win_rate < 45% → поднять порог (входить реже, но лучше)
          win_rate > 60% и много сделок → можно снизить порог
          иначе → не менять
        """
        s = self.get_stats()
        if s.total < MIN_SAMPLES:
            return current_threshold

        if s.win_rate < 0.45:
            new = min(current_threshold + THRESHOLD_STEP, MAX_THRESHOLD)
            log.info("OutcomeLearner: порог ↑ %.2f→%.2f (win_rate=%.1f%%)",
                     current_threshold, new, s.win_rate * 100)
            return new
        elif s.win_rate > 0.60 and s.total >= 100:
            new = max(current_threshold - THRESHOLD_STEP * 0.5, MIN_THRESHOLD)
            log.info("OutcomeLearner: порог ↓ %.2f→%.2f (win_rate=%.1f%%)",
                     current_threshold, new, s.win_rate * 100)
            return new

        return current_threshold

    def suggest_sl_tp_mult(self) -> tuple[float, float]:
        """
        Предлагает оптимальные множители SL/TP на основе истории.

        Если большинство закрытий по SL → SL слишком близко → увеличить mult.
        Если большинство по timeout → TP слишком далеко → уменьшить mult.
        """
        if len(self._trades) < MIN_SAMPLES:
            return 1.5, 2.5

        sl_exits = sum(1 for t in self._trades if t["exit"] == "sl_hit")
        tp_exits = sum(1 for t in self._trades if t["exit"] == "tp_hit")
        timeout_exits = sum(1 for t in self._trades if t["exit"] == "timeout")
        total = len(self._trades)

        sl_ratio = sl_exits / total
        tp_ratio = tp_exits / total
        timeout_ratio = timeout_exits / total

        sl_mult = self.stats.optimal_sl_mult
        tp_mult = self.stats.optimal_tp_mult

        if sl_ratio > 0.6:
            sl_mult = min(sl_mult + 0.2, 3.0)
        elif sl_ratio < 0.2 and tp_ratio < 0.3:
            sl_mult = max(sl_mult - 0.1, 0.8)

        if timeout_ratio > 0.4:
            tp_mult = max(tp_mult - 0.3, 1.5)
        elif tp_ratio > 0.5:
            tp_mult = min(tp_mult + 0.2, 4.0)

        return round(sl_mult, 2), round(tp_mult, 2)

    def load_from_db(self) -> None:
        """Загружает историю сделок из БД при старте."""
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT net_pnl, hold_time_ms, exit_reason
                    FROM futures_paper_trades
                    WHERE model_scope=? AND closed_at_utc IS NOT NULL
                    ORDER BY closed_at_utc DESC LIMIT ?
                    """,
                    (self.model_scope, WINDOW),
                ).fetchall()
            for row in reversed(rows):
                self._trades.append({
                    "pnl": float(row[0] or 0),
                    "hold_ms": int(row[1] or 0),
                    "exit": str(row[2] or ""),
                    "sl_mult": 1.5,
                    "tp_mult": 2.5,
                })
            if self._trades:
                self._update_stats()
                log.info("OutcomeLearner: загружено %d сделок из БД", len(self._trades))
        except Exception as exc:
            log.warning("OutcomeLearner.load_from_db: %s", exc)

    # ── Internal ──────────────────────────────────────────────

    def _update_stats(self) -> None:
        trades = list(self._trades)
        if not trades:
            return

        pnls = [t["pnl"] for t in trades]
        wins  = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        self.stats = OutcomeStats(
            total=len(trades),
            wins=len(wins),
            win_rate=len(wins) / len(trades),
            avg_win_usdt=sum(wins) / len(wins) if wins else 0.0,
            avg_loss_usdt=abs(sum(losses) / len(losses)) if losses else 0.0,
            total_pnl=sum(pnls),
            avg_hold_ms=sum(t["hold_ms"] for t in trades) / len(trades),
            optimal_sl_mult=self.stats.optimal_sl_mult,
            optimal_tp_mult=self.stats.optimal_tp_mult,
        )

        sl_mult, tp_mult = self.suggest_sl_tp_mult()
        self.stats.optimal_sl_mult = sl_mult
        self.stats.optimal_tp_mult = tp_mult
