"""
Historian — Model 1: обнаружение паттернов и режима рынка.

Обучается на БОЛЬШОМ объёме исторических данных (batch).
Запускается тяжёлым bootstrap-процессом, потом раз в день инкрементально.

Выход:
  regime: 'trend' | 'chop' | 'spike' | 'unknown'
  pattern_score: float 0..1 (насколько текущий паттерн похож на прибыльные входы)

Использует: GradientBoostingClassifier из sklearn (без доп. зависимостей).
"""
from __future__ import annotations

import logging

import numpy as np

from src.botik.ml.base_model import BaseModel, TrainResult

log = logging.getLogger("botik.ml.historian")

REGIMES = ["trend", "chop", "spike", "unknown"]


class Historian(BaseModel):
    model_name = "historian"
    min_accuracy = 0.52
    min_trades = 100

    def __init__(self, model_scope: str = "futures") -> None:
        super().__init__()
        self.model_scope = model_scope
        self._regime_model = None       # классификатор режима
        self._pattern_model = None      # скоринг паттернов

    def _build_models(self):
        from sklearn.ensemble import GradientBoostingClassifier
        self._regime_model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4,
            learning_rate=0.05, subsample=0.8,
            random_state=42,
        )
        self._pattern_model = GradientBoostingClassifier(
            n_estimators=150, max_depth=3,
            learning_rate=0.05, subsample=0.8,
            random_state=42,
        )

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> TrainResult:
        if len(X) < self.min_trades:
            log.warning("Historian: недостаточно данных (%d < %d)", len(X), self.min_trades)
            return TrainResult(accuracy=0.0, trade_count=len(X))

        self._build_models()

        # Разметка режима: простая эвристика по индексу фичей
        # price_change_20 (idx 2) и atr_14 (idx 3)
        regimes = self._classify_regimes(X)

        try:
            from sklearn.model_selection import cross_val_score

            # Паттерн модель: предсказывает прибыльность (y)
            sw = sample_weight if sample_weight is not None else np.ones(len(X))
            self._pattern_model.fit(X, y, sample_weight=sw)

            # Кросс-валидация для оценки accuracy
            scores = cross_val_score(
                self._pattern_model, X, y,
                cv=min(5, len(X) // 20),
                scoring="accuracy",
            )
            accuracy = float(np.mean(scores))

            # Режим модель
            if len(set(regimes)) > 1:
                self._regime_model.fit(X, regimes)

            self._fitted = True
            self._accuracy = accuracy
            self._trade_count = len(X)
            self._model = self._pattern_model   # главная модель

            log.info(
                "Historian.fit: scope=%s samples=%d accuracy=%.3f",
                self.model_scope, len(X), accuracy,
            )
            return TrainResult(
                accuracy=accuracy,
                trade_count=len(X),
                epochs_done=1,
                extra={"regimes_dist": {r: int(np.sum(np.array(regimes) == r)) for r in REGIMES}},
            )

        except Exception as exc:
            log.error("Historian.fit error: %s", exc)
            return TrainResult(accuracy=0.0, trade_count=len(X))

    def predict(self, features: np.ndarray) -> float:
        """Возвращает pattern_score 0..1 — насколько паттерн похож на прибыльный вход."""
        if not self._fitted or self._pattern_model is None:
            return 0.5
        try:
            x = features.reshape(1, -1)
            proba = self._pattern_model.predict_proba(x)[0]
            return float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            return 0.5

    def predict_regime(self, features: np.ndarray) -> str:
        """Определяет режим рынка по текущим фичам."""
        if not self._fitted or self._regime_model is None:
            return "unknown"
        try:
            x = features.reshape(1, -1)
            return str(self._regime_model.predict(x)[0])
        except Exception:
            return "unknown"

    # ── Internal ──────────────────────────────────────────────

    def _classify_regimes(self, X: np.ndarray) -> list[str]:
        """
        Эвристическая разметка режима для обучения regime_model.
        Индексы фичей из feature_engine.py:
          2  = price_change_20
          3  = atr_14
          6  = volume_ratio_5
          13 = spike_bps
        """
        regimes = []
        for row in X:
            pc20   = float(row[2])  if len(row) > 2  else 0.0
            atr    = float(row[3])  if len(row) > 3  else 0.0
            vr5    = float(row[6])  if len(row) > 6  else 1.0
            spike  = abs(float(row[13])) if len(row) > 13 else 0.0

            if spike > 80 and vr5 > 2.0:
                regimes.append("spike")
            elif abs(pc20) > 150 and atr > 0.01:
                regimes.append("trend")
            elif atr < 0.003:
                regimes.append("chop")
            else:
                regimes.append("trend")
        return regimes
