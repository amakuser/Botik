"""
Predictor — Model 2: live сигнал входа.

Обновляется онлайн после каждой закрытой сделки.
Использует контекст от Historian (pattern_score) как дополнительную фичу.

Выход: entry_prob 0..1 — вероятность прибыльного входа прямо сейчас.
Порог входа: 0.55 (корректируется OutcomeLearner-ом).

Алгоритм: GradientBoostingClassifier с инкрементальным дообучением
через warm_start=True (не теряет старые знания).
"""
from __future__ import annotations

import logging

import numpy as np

from src.botik.ml.base_model import BaseModel, TrainResult

log = logging.getLogger("botik.ml.predictor")

DEFAULT_THRESHOLD = 0.55


class Predictor(BaseModel):
    model_name = "predictor"
    min_accuracy = 0.52
    min_trades = 50

    def __init__(self, model_scope: str = "futures") -> None:
        super().__init__()
        self.model_scope = model_scope
        self.entry_threshold = DEFAULT_THRESHOLD   # корректируется OutcomeLearner

    def _build_model(self, n_estimators: int = 100):
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.8,
            warm_start=True,    # позволяет дообучать без потери старых деревьев
            random_state=42,
        )

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> TrainResult:
        if len(X) < self.min_trades:
            log.warning("Predictor: мало данных (%d)", len(X))
            return TrainResult(accuracy=0.0, trade_count=len(X))

        sw = sample_weight if sample_weight is not None else np.ones(len(X))

        try:
            from sklearn.model_selection import train_test_split

            # Разделяем на train/val для оценки
            X_tr, X_val, y_tr, y_val, sw_tr, _ = train_test_split(
                X, y, sw, test_size=0.2, random_state=42
            )

            if self._model is None:
                self._model = self._build_model(n_estimators=100)
            else:
                # Инкрементальное дообучение: добавляем деревья
                current_n = self._model.n_estimators
                self._model.n_estimators = current_n + 20
                log.debug("Predictor: incremental fit +20 trees (total=%d)", self._model.n_estimators)

            self._model.fit(X_tr, y_tr, sample_weight=sw_tr)

            y_pred = self._model.predict(X_val)
            accuracy = float(np.mean(y_pred == y_val))

            self._fitted = True
            self._accuracy = accuracy
            self._trade_count = len(X)

            log.info(
                "Predictor.fit: scope=%s samples=%d accuracy=%.3f threshold=%.2f",
                self.model_scope, len(X), accuracy, self.entry_threshold,
            )
            return TrainResult(accuracy=accuracy, trade_count=len(X), epochs_done=1)

        except Exception as exc:
            log.error("Predictor.fit error: %s", exc)
            return TrainResult(accuracy=0.0, trade_count=len(X))

    def predict(self, features: np.ndarray) -> float:
        """Возвращает вероятность прибыльного входа 0..1."""
        if not self._fitted or self._model is None:
            return 0.0
        try:
            x = features.reshape(1, -1)
            proba = self._model.predict_proba(x)[0]
            return float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            return 0.0

    def should_enter(self, features: np.ndarray, pattern_score: float = 0.5) -> bool:
        """
        Итоговое решение: входить ли в сделку.
        Комбинирует предсказание модели с pattern_score от Historian.
        """
        if not self._fitted:
            # До обучения — входим только по правилам стратегии
            return True

        prob = self.predict(features)
        # Взвешенная комбинация: 70% predictor + 30% historian
        combined = prob * 0.7 + pattern_score * 0.3
        return combined >= self.entry_threshold
