# -*- coding: utf-8 -*-
"""
Признаки для ML по истории сделок (Python, pandas/numpy).

Из таблицы trades строим матрицу X (strategy_id, symbol, side, qty, price в one-hot/числа)
и целевой вектор y: 1 = прибыльная сделка, 0 = убыточная (классификация).
"""
import logging
from typing import Any, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("ml.features")


def trades_to_dataframe(trades: List[dict]) -> pd.DataFrame:
    """Список сделок в DataFrame."""
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades)


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Матрица признаков X и целевой y из сделок.
    X: strategy_id, symbol, side (one-hot), qty, price.
    y: 1 если pnl > 0, иначе 0 (классификация исхода).
    """
    if df.empty or len(df) < 10:
        return np.zeros((0, 1)), None

    df = df.copy()
    df["strategy_id"] = df["strategy_id"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    df["side"] = df["side"].astype(str)
    df["win"] = (df["pnl"].fillna(0) > 0).astype(int)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)

    X = pd.get_dummies(df[["strategy_id", "symbol", "side", "qty", "price"]], drop_first=True)
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    X = X.fillna(0).values
    y = df["win"].values
    return X, y


def build_position_size_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Признаки и цель для регрессии размера позиции: множитель 0.5--1.0 по rolling win rate."""
    if df.empty or len(df) < 20:
        return np.zeros((0, 1)), np.zeros(0)

    df = df.copy()
    df["strategy_id"] = pd.Categorical(df["strategy_id"])
    df["symbol"] = pd.Categorical(df["symbol"])
    df["win"] = (df["pnl"].fillna(0) > 0).astype(int)
    # Rolling win rate as feature
    df["rolling_win_rate"] = df.groupby("strategy_id")["win"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean()
    )
    df = df.dropna(subset=["rolling_win_rate"])
    if df.empty:
        return np.zeros((0, 1)), np.zeros(0)

    X = df[["rolling_win_rate", "qty", "price"]].fillna(0).values
    # Target: 1.0 if win else 0.5 (reduce size after loss)
    y = np.where(df["win"].values > 0, 1.0, 0.5)
    return X, y
