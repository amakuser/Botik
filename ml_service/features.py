"""
Признаки для ML: из агрегатов (metrics) и при необходимости из fills.
Интерфейс общий — позже можно заменить источник на PyTorch-датасет без смены контракта.
"""
from __future__ import annotations

from typing import Any


def build_features_row(
    mid: float,
    spread_ticks: int,
    imbalance_top_n: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, float]:
    """
    Один вектор признаков для момента времени (по одной строке metrics).
    Расширяемый: extra может содержать лаги, скользящие средние и т.д.
    """
    row = {
        "mid": mid,
        "spread_ticks": float(spread_ticks),
        "imbalance_top_n": imbalance_top_n,
    }
    if extra:
        row.update(extra)
    return row


def feature_names() -> list[str]:
    """Имена признаков по порядку (для sklearn и совместимости с другими бэкендами)."""
    return ["mid", "spread_ticks", "imbalance_top_n"]


# --- Как проверить: build_features_row(50000, 2, 0.1) и проверить ключи.
# --- Частые ошибки: не нормализовать mid при смене символа (разные масштабы).
# --- Что улучшить позже: лаги, rolling mean/std, символ как категория или отдельные модели.
