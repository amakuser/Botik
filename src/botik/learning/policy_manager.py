"""
Model loading/prediction helpers for policy selection.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import numpy as np

from ml_service.train import load_model_bundle, predict_batch as model_predict_batch
from src.botik.storage.sqlite_store import get_active_model


@dataclass(frozen=True)
class ModelBundle:
    model_id: str
    payload: dict[str, Any]


def load_active_model(conn: sqlite3.Connection) -> ModelBundle | None:
    active = get_active_model(conn)
    if not active:
        return None
    model_id = str(active.get("model_id") or "").strip()
    model_path = str(active.get("path_or_payload") or "").strip()
    if not model_id or not model_path:
        return None
    payload = load_model_bundle(model_path)
    return ModelBundle(model_id=model_id, payload=payload)


def predict_batch(model: ModelBundle, features_matrix: np.ndarray) -> np.ndarray:
    out = model_predict_batch(model.payload, features_matrix)
    edge = out.get("expected_net_edge_bps")
    if edge is not None:
        return np.array(edge, dtype=float)
    open_prob = out.get("open_probability")
    if open_prob is None:
        return np.zeros((features_matrix.shape[0],), dtype=float)
    return np.array(open_prob, dtype=float)


def predict_with_details(model: ModelBundle, features_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out = model_predict_batch(model.payload, features_matrix)
    open_prob = out.get("open_probability")
    edge = out.get("expected_net_edge_bps")
    if open_prob is None:
        open_prob = np.zeros((features_matrix.shape[0],), dtype=float)
    if edge is None:
        edge = np.zeros((features_matrix.shape[0],), dtype=float)
    return np.array(open_prob, dtype=float), np.array(edge, dtype=float)
