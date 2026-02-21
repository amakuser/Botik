"""
Оценка модели: сравнение с текущей активной в model_registry.
Гейт: активировать новую модель только если лучше текущей (по метрике).
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_model(path_or_payload: str) -> Any:
    """Загружает модель из пути (pickle). Для PyTorch позже — другой формат."""
    with open(path_or_payload, "rb") as f:
        obj = pickle.load(f)
    if isinstance(obj, dict) and "model" in obj:
        return obj["model"], obj.get("scaler")
    return obj, None


def predict_proba_one(model_and_scaler: tuple[Any, Any], features: list[float]) -> float:
    """Вероятность класса 1 (прибыльность). model_and_scaler = (model, scaler) из load_model."""
    model, scaler = model_and_scaler
    import numpy as np
    X = np.array([features], dtype=float)
    if scaler is not None:
        X = scaler.transform(X)
    if hasattr(model, "predict_proba"):
        return float(model.predict_proba(X)[0, 1])
    return float(model.predict(X)[0])


def is_better_than_current(new_metrics: dict, current_metrics_json: str | None) -> bool:
    """
    Сравнивает новую модель с текущей. Если current нет — считаем новую лучшей.
    Метрика: mean_accuracy (или другая из new_metrics).
    """
    if not current_metrics_json:
        return True
    import json
    try:
        current = json.loads(current_metrics_json)
    except Exception:
        return True
    new_acc = new_metrics.get("mean_accuracy", 0)
    cur_acc = current.get("mean_accuracy", 0)
    return new_acc > cur_acc


# --- Как проверить: обучить две модели, сравнить через is_better_than_current.
# --- Частые ошибки: не учитывать scaler при инференсе; разный порядок признаков.
# --- Что улучшить позже: несколько метрик (precision, recall); порог для активации.
