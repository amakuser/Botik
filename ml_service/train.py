"""
Offline-обучение: sklearn, батчами. Метка y — бинарная прибыльность на горизонте (с учётом комиссий).
Интерфейс так, чтобы позже заменить на PyTorch без смены контракта (train_model(X, y) -> model_id, path, metrics).
"""
from __future__ import annotations

import json
import logging
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def train_model(
    X: list[list[float]],
    y: list[float],
    model_dir: str | Path = "data/models",
) -> tuple[str, str, dict]:
    """
    Обучает модель (sklearn RandomForest). Возвращает (model_id, path_or_payload, metrics_dict).
    Для совместимости с model_registry: path_or_payload — путь к сохранённому pickle или base64 (здесь — путь).
    """
    if len(X) < 100 or len(y) < 100:
        logger.warning("Мало данных для обучения: %d строк", len(X))
        return "", "", {}
    import numpy as np  # noqa: I001
    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=float)
    tscv = TimeSeriesSplit(n_splits=3)
    clf = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
    scaler = StandardScaler()
    scores = []
    for train_idx, test_idx in tscv.split(X_arr):
        X_train, X_test = X_arr[train_idx], X_arr[test_idx]
        y_train, y_test = y_arr[train_idx], y_arr[test_idx]
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
        clf.fit(X_train, y_train)
        scores.append(clf.score(X_test, y_test))
    mean_score = float(sum(scores) / len(scores)) if scores else 0.0
    model_id = f"rf-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:8]}"
    path = Path(model_dir)
    path.mkdir(parents=True, exist_ok=True)
    out_path = path / f"{model_id}.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({"model": clf, "scaler": scaler}, f)
    metrics = {"mean_accuracy": mean_score, "splits": len(scores)}
    return model_id, str(out_path), metrics


# --- Как проверить: передать X, y из dataset.get_feature_matrix_and_labels, проверить что создаётся файл и возвращается model_id.
# --- Частые ошибки: не масштабировать признаки (разный масштаб mid и spread_ticks); утечка будущего при walk-forward.
# --- Что улучшить позже: PyTorch-модель с тем же интерфейсом; сохранение в model_registry из run_loop.
