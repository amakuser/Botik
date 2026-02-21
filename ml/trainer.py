# -*- coding: utf-8 -*-
"""
Обучение и сохранение ML-модели (Python, scikit-learn).

Классификатор исхода сделки (win/loss); сохранение через joblib.
apply_model_to_params — заглушка для предсказания по одной сделке (в проде нужны сохранённые энкодеры).
"""
import logging
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

log = logging.getLogger("ml.trainer")

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    GradientBoostingClassifier = None
    StandardScaler = None


def train_outcome_model(X: np.ndarray, y: np.ndarray) -> Any:
    """Обучить классификатор исхода сделки (X, y). Возвращает (model, scaler)."""
    if not HAS_SKLEARN or X.size == 0 or len(X) < 10:
        return None, None
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=42)
    model.fit(Xs, y)
    return model, scaler


def train_position_size_model(X: np.ndarray, y: np.ndarray) -> Any:
    """Обучить регрессор множителя размера позиции (опционально)."""
    if not HAS_SKLEARN or X.size == 0 or len(X) < 10:
        return None, None
    from sklearn.ensemble import GradientBoostingRegressor
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = GradientBoostingRegressor(n_estimators=50, max_depth=3, random_state=42)
    model.fit(Xs, y)
    return model, scaler


def save_model(model: Any, scaler: Any, path: str, meta: Optional[dict] = None) -> None:
    """Сохранить модель и scaler в файл (joblib)."""
    try:
        import joblib
    except ImportError:
        log.warning("joblib not installed; model not saved")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "scaler": scaler, "meta": meta or {}}
    joblib.dump(payload, path)
    log.info("Model saved to %s", path)


def load_model(path: str) -> tuple[Any, Any, dict]:
    """Загрузить модель, scaler и meta из файла."""
    try:
        import joblib
    except ImportError:
        return None, None, {}
    p = Path(path)
    if not p.exists():
        return None, None, {}
    payload = joblib.load(p)
    return payload.get("model"), payload.get("scaler"), payload.get("meta", {})


def apply_model_to_params(
    model: Any,
    scaler: Any,
    strategy_id: str,
    symbol: str,
    qty: float,
    price: float,
    side: str,
) -> dict[str, Any]:
    """
    Предсказание вероятности успеха или множителя размера (заглушка: в проде нужны те же энкодеры, что при обучении).
    """
    if model is None or scaler is None:
        return {}
    try:
        # Minimal feature vector for single prediction
        from sklearn.preprocessing import LabelEncoder
        # Simplified: use strategy_id hash, symbol hash, qty, price, side
        le_s = LabelEncoder()
        le_sym = LabelEncoder()
        le_side = LabelEncoder()
        # For single row we need same encoding as training; in production use saved encoders
        X = np.array([[hash(strategy_id) % 1000, hash(symbol) % 1000, qty, price, hash(side) % 10]])
        Xs = scaler.transform(X)
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(Xs)[0, 1]
            return {"win_probability": float(proba), "position_size_multiplier": 0.5 + 0.5 * proba}
        return {}
    except Exception as e:
        log.debug("apply_model_to_params: %s", e)
        return {}
