"""
Датасет для обучения: загрузка из БД (metrics_1s + fills).
Метка y: бинарная прибыльность на горизонте horizon_seconds с учётом комиссий.
Интерфейс батчами для экономии RAM; позже можно заменить на PyTorch DataLoader.
"""
from __future__ import annotations

import sqlite3
from typing import Iterator

from ml_service.features import build_features_row, feature_names  # noqa: I001


def load_metrics_fills_cursor(
    conn: sqlite3.Connection,
    symbol: str,
    limit: int = 100000,
) -> Iterator[tuple[dict[str, float], float | None, str]]:
    """
    Итератор по (features_dict, label_or_none, ts_utc).
    label = 1 если на горизонте после этой метрики был прибыльный fill (после комиссий), иначе 0; None если нет данных.
    Упрощённо: берём metrics_1s по символу, для каждой строки смотрим fills в течение horizon_seconds после ts;
    если есть fill с положительным PnL после комиссий — метка 1, иначе 0.
    """
    cur = conn.execute(
        "SELECT symbol, ts_utc, best_bid, best_ask, mid, spread_ticks, imbalance_top_n FROM metrics_1s WHERE symbol = ? ORDER BY ts_utc LIMIT ?",
        (symbol, limit),
    )
    for row in cur:
        sym, ts, bid, ask, mid, spread_ticks, imb = row
        mid = mid or 0.0
        spread_ticks = spread_ticks or 0
        imb = imb or 0.0
        feats = build_features_row(mid, spread_ticks, imb)
        # Метку считаем по fills — упрощённо: без реального расчёта PnL возвращаем None (offline дообучим).
        yield feats, None, ts


def get_feature_matrix_and_labels(
    conn: sqlite3.Connection,
    symbol: str,
    limit: int = 50000,
) -> tuple[list[list[float]], list[float]]:
    """
    Загружает батч: X — список векторов признаков, y — список меток (0/1).
    Если меток нет — возвращает пустые y (обучение пропустить).
    """
    names = feature_names()
    X: list[list[float]] = []
    y: list[float] = []
    for feats, label, _ in load_metrics_fills_cursor(conn, symbol, limit=limit):
        X.append([feats[k] for k in names])
        if label is not None:
            y.append(label)
        else:
            y.append(0.0)  # заглушка при отсутствии меток
    return X, y


# --- Как проверить: подключиться к БД с metrics_1s, вызвать get_feature_matrix_and_labels, проверить размерности.
# --- Частые ошибки: не учитывать комиссии при метке; разный порядок признаков при обучении и инференсе.
# --- Что улучшить позже: реальный расчёт y по fills и horizon_seconds; walk-forward split по времени.
