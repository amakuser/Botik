"""
Incremental lifecycle ML trainer.

Model stack:
- classifier: label_open (SGDClassifier, log_loss)
- regressor: expected net_edge_bps (SGDRegressor)
"""
from __future__ import annotations

import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import SGDClassifier, SGDRegressor
from sklearn.preprocessing import StandardScaler


def _utc_now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    clipped = np.clip(x, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _align_feature_count(X: np.ndarray, expected_cols: int) -> np.ndarray:
    if X.ndim != 2:
        return X
    cols = int(X.shape[1])
    target = max(int(expected_cols), 1)
    if cols == target:
        return X
    if cols > target:
        return X[:, :target]
    pad = np.zeros((X.shape[0], target - cols), dtype=float)
    return np.hstack([X, pad])


def train_lifecycle_models(
    X: np.ndarray,
    y_open: np.ndarray,
    y_edge: np.ndarray,
    *,
    batch_size: int = 64,
    model_dir: str | Path = "data/models",
) -> tuple[str, str, dict[str, Any]]:
    rows = int(X.shape[0]) if X.ndim == 2 else 0
    if rows < 20:
        return "", "", {}

    scaler = StandardScaler()
    clf = SGDClassifier(loss="log_loss", random_state=42)
    reg = SGDRegressor(loss="huber", random_state=42)

    classes = np.array([0, 1], dtype=int)
    step = max(int(batch_size), 8)
    reg_samples = 0

    for start in range(0, rows, step):
        end = min(start + step, rows)
        X_batch = X[start:end]
        y_open_batch = y_open[start:end]
        y_edge_batch = y_edge[start:end]

        scaler.partial_fit(X_batch)
        Xs = scaler.transform(X_batch)
        clf.partial_fit(Xs, y_open_batch, classes=classes)

        edge_mask = ~np.isnan(y_edge_batch)
        if np.any(edge_mask):
            reg.partial_fit(Xs[edge_mask], y_edge_batch[edge_mask])
            reg_samples += int(np.sum(edge_mask))

    X_scaled = scaler.transform(X)
    open_pred = clf.predict(X_scaled)
    open_acc = float(np.mean(open_pred == y_open)) if rows else 0.0
    positive_ratio = float(np.mean(y_open == 1)) if rows else 0.0

    edge_mask_all = ~np.isnan(y_edge)
    edge_mae = None
    if reg_samples > 0 and np.any(edge_mask_all):
        edge_pred = reg.predict(X_scaled[edge_mask_all])
        edge_true = y_edge[edge_mask_all]
        edge_mae = float(np.mean(np.abs(edge_pred - edge_true)))

    model_id = f"lifecycle-sgd-{_utc_now_tag()}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{model_id}.pkl"
    payload = {
        "model_id": model_id,
        "scaler": scaler,
        "clf_open": clf,
        "reg_edge": reg if reg_samples > 0 else None,
        "trained_rows": rows,
        "reg_samples": reg_samples,
    }
    with out_path.open("wb") as f:
        pickle.dump(payload, f)

    metrics: dict[str, Any] = {
        "quality_score": open_acc,
        "open_accuracy": open_acc,
        "positive_ratio": positive_ratio,
        "trained_rows": rows,
        "reg_samples": reg_samples,
    }
    if edge_mae is not None:
        metrics["edge_mae"] = edge_mae

    return model_id, str(out_path), metrics


def load_model_bundle(path_or_payload: str) -> dict[str, Any]:
    with open(path_or_payload, "rb") as f:
        obj = pickle.load(f)
    if not isinstance(obj, dict):
        raise ValueError("Invalid model payload format")
    return obj


def predict_batch(bundle: dict[str, Any], X: np.ndarray) -> dict[str, np.ndarray]:
    scaler: StandardScaler = bundle["scaler"]
    clf: SGDClassifier = bundle["clf_open"]
    reg: SGDRegressor | None = bundle.get("reg_edge")

    expected_cols = int(getattr(scaler, "n_features_in_", X.shape[1] if X.ndim == 2 else 1))
    X_aligned = _align_feature_count(np.array(X, dtype=float), expected_cols)
    Xs = scaler.transform(X_aligned)
    if hasattr(clf, "predict_proba"):
        open_proba = clf.predict_proba(Xs)[:, 1]
    else:
        decision = clf.decision_function(Xs)
        open_proba = _sigmoid(np.array(decision, dtype=float))

    out: dict[str, np.ndarray] = {"open_probability": np.array(open_proba, dtype=float)}
    if reg is not None:
        out["expected_net_edge_bps"] = np.array(reg.predict(Xs), dtype=float)
    return out


def train_model(
    X: list[list[float]],
    y: list[float],
    model_dir: str | Path = "data/models",
) -> tuple[str, str, dict]:
    """
    Backward-compatible wrapper for old call-sites.
    """
    X_arr = np.array(X, dtype=float)
    y_open = np.array(y, dtype=int)
    y_edge = np.full((len(y_open),), np.nan, dtype=float)
    return train_lifecycle_models(X_arr, y_open, y_edge, batch_size=64, model_dir=model_dir)
