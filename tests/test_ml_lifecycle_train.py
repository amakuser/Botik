from __future__ import annotations

from pathlib import Path

import numpy as np

from ml_service.train import load_model_bundle, predict_batch, train_lifecycle_models


def test_train_lifecycle_models_and_predict(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    rows = 120
    cols = 24
    X = rng.normal(0.0, 1.0, size=(rows, cols))
    y_open = (X[:, 0] + 0.3 * X[:, 1] > 0).astype(int)
    y_edge = (X[:, 0] * 3.0 + X[:, 2]).astype(float)
    y_edge[::7] = np.nan

    model_id, model_path, metrics = train_lifecycle_models(
        X,
        y_open,
        y_edge,
        batch_size=32,
        model_dir=tmp_path,
    )
    assert model_id
    assert Path(model_path).exists()
    assert metrics["trained_rows"] == rows
    assert "open_accuracy" in metrics

    bundle = load_model_bundle(model_path)
    pred = predict_batch(bundle, X[:5])
    assert "open_probability" in pred
    assert len(pred["open_probability"]) == 5
