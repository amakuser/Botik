"""
Labeler — авторазметка исторических данных для cold start.

Берёт price_history из БД и генерирует labeled_samples:
  label=1 если цена через N свечей выросла на X%
  label=0 иначе

source='historical' — отличается от 'live_trade' (реальные сделки)

При обучении live_trade записи имеют больший вес (LIVE_WEIGHT_MULT).

Запуск:
  from src.botik.ml.labeler import Labeler
  labeler = Labeler(model_scope='futures')
  count = labeler.run(symbol='BTCUSDT')
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

import numpy as np

from src.botik.ml.feature_engine import (
    build_futures_features,
    build_spot_features,
    load_candles_from_db,
    FUTURES_FEATURE_DIM,
    SPOT_FEATURE_DIM,
)
from src.botik.storage.db import get_db

log = logging.getLogger("botik.ml.labeler")

# Параметры разметки
FORWARD_CANDLES = 5        # смотрим вперёд на N свечей
PROFIT_TARGET   = 0.008    # 0.8% движение = метка 1 (long)
LOSS_TARGET     = -0.006   # -0.6% = метка 0 (short opportunity)
LIVE_WEIGHT_MULT = 3.0     # живые сделки весят в 3 раза больше исторических
MIN_CANDLES = 25           # минимум свечей для построения фичей


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _feature_hash(vec: np.ndarray) -> str:
    """Уникальный хэш вектора фичей для дедупликации."""
    b = vec.tobytes()
    return hashlib.md5(b).hexdigest()


class Labeler:
    """
    Генерирует обучающие образцы из исторических свечей.

    Алгоритм:
      1. Загрузить все свечи для символа
      2. Для каждой позиции i (скользящее окно):
         - Построить фичи из candles[i-MIN_CANDLES:i]
         - Посмотреть что случилось через FORWARD_CANDLES свечей
         - Если max_forward_change > PROFIT_TARGET → label=1
         - Если min_forward_change < LOSS_TARGET → label=0 (для short)
         - Иначе → пропустить (нейтрально)
      3. Записать в labeled_samples
    """

    def __init__(
        self,
        model_scope: str = "futures",
        forward_candles: int = FORWARD_CANDLES,
        profit_target: float = PROFIT_TARGET,
    ) -> None:
        self.model_scope = model_scope
        self.forward_candles = forward_candles
        self.profit_target = profit_target
        self._category = "linear" if model_scope == "futures" else "spot"

    def run(
        self,
        symbol: str,
        interval: str = "1",
        limit: int = 2000,
    ) -> int:
        """
        Размечает исторические данные для одного символа.
        Возвращает количество записанных образцов.
        """
        candles = load_candles_from_db(
            symbol, category=self._category, interval=interval, limit=limit
        )
        if len(candles) < MIN_CANDLES + self.forward_candles + 1:
            log.warning(
                "Labeler %s: недостаточно данных (%d свечей)", symbol, len(candles)
            )
            return 0

        samples: list[tuple] = []

        for i in range(MIN_CANDLES, len(candles) - self.forward_candles):
            window = candles[i - MIN_CANDLES: i]
            future = candles[i: i + self.forward_candles]

            # Строим фичи
            if self.model_scope == "futures":
                vec = build_futures_features(window)
            else:
                vec = build_spot_features(window)

            if vec is None:
                continue

            # Считаем метку
            entry_close = float(candles[i - 1]["close"])
            if entry_close == 0:
                continue

            future_highs  = [float(c["high"])  for c in future]
            future_lows   = [float(c["low"])   for c in future]

            max_move = (max(future_highs) - entry_close) / entry_close
            min_move = (min(future_lows)  - entry_close) / entry_close

            if max_move >= self.profit_target:
                label = 1    # лонг прибыльный
            elif min_move <= -self.profit_target:
                label = 0    # лонг убыточный (шорт возможность)
            else:
                continue     # нейтрально — пропускаем

            feat_hash = _feature_hash(vec)
            feat_json = json.dumps(vec.tolist())
            samples.append((
                feat_hash, symbol, self.model_scope,
                feat_json, label, "historical",
                1.0,        # weight (живые сделки получат LIVE_WEIGHT_MULT)
                _utc_now(),
            ))

        if not samples:
            log.info("Labeler %s: нет образцов после фильтрации", symbol)
            return 0

        written = self._write_samples(samples)
        log.info("Labeler %s: записано %d образцов из %d свечей", symbol, written, len(candles))
        return written

    def label_live_trade(
        self,
        symbol: str,
        features: np.ndarray,
        was_profitable: bool,
    ) -> None:
        """
        Добавляет результат реальной paper-сделки в labeled_samples.
        Эти образцы весят LIVE_WEIGHT_MULT больше исторических.
        """
        label = 1 if was_profitable else 0
        feat_hash = _feature_hash(features)
        feat_json = json.dumps(features.tolist())

        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO labeled_samples
                      (feature_hash, symbol, model_scope, features_json,
                       label, source, weight, created_at_utc)
                    VALUES (?, ?, ?, ?, ?, 'live_trade', ?, ?)
                    """,
                    (feat_hash, symbol, self.model_scope,
                     feat_json, label, LIVE_WEIGHT_MULT, _utc_now()),
                )
        except Exception as exc:
            log.error("label_live_trade error: %s", exc)

    def load_dataset(
        self,
        symbol: str | None = None,
        limit: int = 10000,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Загружает датасет из labeled_samples.
        Возвращает (X, y, weights).
        """
        try:
            db = get_db()
            with db.connect() as conn:
                if symbol:
                    rows = conn.execute(
                        """
                        SELECT features_json, label, weight
                        FROM labeled_samples
                        WHERE model_scope=? AND symbol=?
                        ORDER BY created_at_utc DESC LIMIT ?
                        """,
                        (self.model_scope, symbol, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT features_json, label, weight
                        FROM labeled_samples
                        WHERE model_scope=?
                        ORDER BY created_at_utc DESC LIMIT ?
                        """,
                        (self.model_scope, limit),
                    ).fetchall()
        except Exception as exc:
            log.error("load_dataset error: %s", exc)
            return np.array([]), np.array([]), np.array([])

        if not rows:
            return np.array([]), np.array([]), np.array([])

        X_list, y_list, w_list = [], [], []
        for feat_json, label, weight in rows:
            try:
                vec = np.array(json.loads(feat_json), dtype=np.float32)
                X_list.append(vec)
                y_list.append(int(label))
                w_list.append(float(weight or 1.0))
            except Exception:
                continue

        if not X_list:
            return np.array([]), np.array([]), np.array([])

        return (
            np.array(X_list, dtype=np.float32),
            np.array(y_list, dtype=np.int32),
            np.array(w_list, dtype=np.float32),
        )

    # ── Internal ──────────────────────────────────────────────

    def _write_samples(self, samples: list[tuple]) -> int:
        try:
            db = get_db()
            with db.connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS labeled_samples (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        feature_hash  TEXT UNIQUE NOT NULL,
                        symbol        TEXT NOT NULL,
                        model_scope   TEXT NOT NULL,
                        features_json TEXT NOT NULL,
                        label         INTEGER NOT NULL,
                        source        TEXT NOT NULL DEFAULT 'historical',
                        weight        REAL NOT NULL DEFAULT 1.0,
                        created_at_utc TEXT NOT NULL
                    )
                    """
                )
                written = 0
                for s in samples:
                    try:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO labeled_samples
                              (feature_hash, symbol, model_scope, features_json,
                               label, source, weight, created_at_utc)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            s,
                        )
                        written += 1
                    except Exception:
                        pass
            return written
        except Exception as exc:
            log.error("_write_samples error: %s", exc)
            return 0
