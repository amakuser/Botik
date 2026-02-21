# -*- coding: utf-8 -*-
"""
Пайплайн ML (Python): загрузка сделок из БД -> признаки -> обучение -> сохранение модели.

Вызывается из OrderManager раз в retrain_after_trades сделок (если ml.enabled).
"""
import logging
from typing import Any, Callable, Optional

from stats import storage as stats_storage

from ml.features import build_features, trades_to_dataframe
from ml.trainer import save_model, train_outcome_model

log = logging.getLogger("ml.pipeline")


def run_pipeline(
    db_path: str,
    model_path: str,
    retrain_after_trades: int = 50,
    on_params_updated: Optional[Callable[[str, dict], None]] = None,
) -> bool:
    """
    Загрузить сделки из БД, построить признаки, обучить классификатор исхода, сохранить модель.
    on_params_updated(strategy_id, params) — опциональный колбэк при обновлении параметров.
    """
    trades = stats_storage.get_trades_for_ml(db_path, limit=5000)
    if len(trades) < retrain_after_trades:
        log.info("Not enough trades for retrain (%d < %d)", len(trades), retrain_after_trades)
        return False

    df = trades_to_dataframe(trades)
    X, y = build_features(df)
    if X.size == 0 or y is None:
        return False

    model, scaler = train_outcome_model(X, y)
    if model is None:
        return False

    save_model(model, scaler, model_path, meta={"n_samples": len(trades)})
    log.info("ML pipeline finished; model saved (%d samples)", len(trades))
    return True
