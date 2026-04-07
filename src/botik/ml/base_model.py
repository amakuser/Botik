"""
BaseModel — абстрактный интерфейс для всех ML-моделей.

Три конкретных реализации:
  Historian     — Model 1: паттерны на OHLCV истории
  Predictor     — Model 2: live сигнал входа
  OutcomeLearner— Model 3: обратная связь от результатов сделок

Критерий "модель обучена" (is_ready):
  - fitted = True (был вызван fit хотя бы раз)
  - accuracy > min_accuracy
  - trade_count >= min_trades

Разделение по scope: 'futures' | 'spot' — модели не смешиваются.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class TrainResult:
    """Результат одного запуска обучения."""
    accuracy: float = 0.0
    loss: float = 0.0
    trade_count: int = 0
    epochs_done: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class BaseModel(ABC):
    """
    Базовый класс для всех моделей.

    Подклассы реализуют: fit(), predict(), _build_model().
    Сохранение/загрузка через ModelRegistry.
    """

    model_scope: str = "futures"    # 'futures' | 'spot'
    model_name: str = "base"
    min_accuracy: float = 0.52
    min_trades: int = 50

    def __init__(self) -> None:
        self._fitted: bool = False
        self._accuracy: float = 0.0
        self._trade_count: int = 0
        self._model: Any = None       # sklearn / lgbm объект

    # ── Публичный API ─────────────────────────────────────────

    @abstractmethod
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> TrainResult:
        """Обучить модель. Обновляет _fitted, _accuracy."""
        ...

    @abstractmethod
    def predict(self, features: np.ndarray) -> float:
        """
        Предсказание для одного вектора фичей.
        Возвращает вероятность 0.0–1.0.
        """
        ...

    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        """Предсказание для батча. По умолчанию — поэлементно."""
        return np.array([self.predict(row) for row in X])

    def is_ready(self) -> bool:
        """Достаточно ли модель обучена для торговли."""
        return (
            self._fitted
            and self._accuracy >= self.min_accuracy
            and self._trade_count >= self.min_trades
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_scope": self.model_scope,
            "fitted": self._fitted,
            "accuracy": round(self._accuracy, 4),
            "trade_count": self._trade_count,
            "is_ready": self.is_ready(),
        }

    def get_model_object(self) -> Any:
        """Вернуть внутренний объект модели для сохранения."""
        return self._model

    def set_model_object(self, obj: Any, accuracy: float, trade_count: int) -> None:
        """Восстановить модель из сохранённого состояния."""
        self._model = obj
        self._fitted = True
        self._accuracy = accuracy
        self._trade_count = trade_count
