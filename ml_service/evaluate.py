"""
Model evaluation / gating helpers for lifecycle ML models.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from ml_service.train import load_model_bundle, predict_batch


def load_model(path_or_payload: str) -> Any:
    """
    Backward-compatible loader that returns (bundle, None).
    """
    bundle = load_model_bundle(path_or_payload)
    return bundle, None


def predict_proba_one(model_and_scaler: tuple[Any, Any], features: list[float]) -> float:
    """
    Backward-compatible API used by legacy call-sites.
    """
    bundle, _ = model_and_scaler
    X = np.array([features], dtype=float)
    pred = predict_batch(bundle, X)
    values = pred.get("open_probability")
    if values is None or len(values) == 0:
        return 0.0
    return float(values[0])


def is_better_than_current(new_metrics: dict, current_metrics_json: str | None) -> bool:
    """
    Compare by quality_score, fallback to open_accuracy/mean_accuracy.
    """
    if not current_metrics_json:
        return True
    try:
        current = json.loads(current_metrics_json)
    except Exception:
        return True

    new_score = float(
        new_metrics.get("quality_score")
        or new_metrics.get("open_accuracy")
        or new_metrics.get("mean_accuracy")
        or 0.0
    )
    cur_score = float(
        current.get("quality_score")
        or current.get("open_accuracy")
        or current.get("mean_accuracy")
        or 0.0
    )
    return new_score > cur_score
