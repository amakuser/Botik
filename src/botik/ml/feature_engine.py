"""
FeatureEngine — строит векторы фичей для ML-моделей.

Два набора фичей:
  build_futures_features() — для фьючерсных моделей
  build_spot_features()    — для спотовых моделей (задача #7)

Источники данных:
  - price_history (OHLCV из БД)
  - orderbook (текущий стакан из TradingState)

Фичи сохраняются в data/features/*.npz для быстрой загрузки при обучении.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger("botik.ml.feature_engine")

FEATURES_DIR = Path(__file__).resolve().parents[4] / "data" / "features"
FEATURES_DIR.mkdir(parents=True, exist_ok=True)

# Размерность векторов фичей
FUTURES_FEATURE_DIM = 18
SPOT_FEATURE_DIM = 14


# ── Имена фичей (для документации и дебага) ──────────────────

FUTURES_FEATURE_NAMES = [
    # Ценовой импульс
    "price_change_1",    # изменение цены за 1 свечу, bps
    "price_change_5",    # за 5 свечей
    "price_change_20",   # за 20 свечей
    # Волатильность
    "atr_14",            # ATR(14) нормализованный к цене
    "atr_5",             # ATR(5) — краткосрочная волатильность
    "high_low_range",    # (high-low)/close последней свечи
    # Объём
    "volume_ratio_5",    # объём / средний_объём(5)
    "volume_ratio_20",   # объём / средний_объём(20)
    "volume_trend",      # наклон объёма (растёт/падает)
    # Паттерн свечей
    "body_ratio",        # размер тела / диапазон (0=доджи, 1=полная свеча)
    "upper_shadow",      # верхняя тень / диапазон
    "lower_shadow",      # нижняя тень / диапазон
    # Спайк
    "spike_bps",         # величина последнего спайка
    "spike_direction",   # направление: +1/-1
    # RSI (упрощённый)
    "rsi_14",            # RSI(14), нормализованный 0..1
    # Позиция цены
    "price_vs_high20",   # насколько цена ниже максимума 20 свечей (0..1)
    "price_vs_low20",    # насколько цена выше минимума 20 свечей (0..1)
    # Orderbook
    "ob_imbalance",      # bid_vol/(bid_vol+ask_vol), 0..1
]

SPOT_FEATURE_NAMES = [
    "spread_bps",
    "depth_imbalance",
    "trades_per_min",
    "price_change_1",
    "price_change_5",
    "volume_ratio_5",
    "atr_14",
    "body_ratio",
    "rsi_14",
    "price_vs_high20",
    "price_vs_low20",
    "ob_imbalance",
    "ask_depth_quote",
    "bid_depth_quote",
]


# ── Вспомогательные функции ───────────────────────────────────

def _safe(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.5
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    gains = gains[-period:]
    losses = losses[-period:]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 1.0
    rs = avg_gain / avg_loss
    rsi = rs / (1 + rs)
    return round(rsi, 4)


def _calc_atr_norm(highs: list[float], lows: list[float],
                   closes: list[float], period: int = 14) -> float:
    """ATR нормализованный к последней цене."""
    if len(highs) < period + 1 or closes[-1] == 0:
        return 0.0
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return round(atr / closes[-1], 6)


# ── Основные функции ──────────────────────────────────────────

def build_futures_features(
    candles: list[dict],       # список {'open','high','low','close','volume'}
    ob_imbalance: float = 0.5, # дисбаланс стакана (0..1)
) -> np.ndarray | None:
    """
    Строит вектор фичей FUTURES_FEATURE_DIM=18 из свечей + стакана.

    candles — список словарей, последний элемент = последняя свеча.
    Минимум 21 свеча для всех фичей.

    Возвращает np.ndarray shape (18,) или None если данных недостаточно.
    """
    if len(candles) < 21:
        return None

    closes = [_safe(c["close"]) for c in candles]
    highs  = [_safe(c["high"])  for c in candles]
    lows   = [_safe(c["low"])   for c in candles]
    vols   = [_safe(c["volume"]) for c in candles]
    opens  = [_safe(c["open"])  for c in candles]

    c = closes[-1]
    if c == 0:
        return None

    # ── Ценовой импульс ───────────────────────────────────────
    price_change_1  = (closes[-1] - closes[-2]) / closes[-2] * 10000 if closes[-2] else 0.0
    price_change_5  = (closes[-1] - closes[-6]) / closes[-6] * 10000 if closes[-6] else 0.0
    price_change_20 = (closes[-1] - closes[-21]) / closes[-21] * 10000 if closes[-21] else 0.0

    # ── Волатильность ─────────────────────────────────────────
    atr_14 = _calc_atr_norm(highs, lows, closes, 14)
    atr_5  = _calc_atr_norm(highs[-6:], lows[-6:], closes[-6:], 5)
    hl = highs[-1] - lows[-1]
    high_low_range = hl / c if c else 0.0

    # ── Объём ─────────────────────────────────────────────────
    avg_vol_5  = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else 1.0
    avg_vol_20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else 1.0
    vol_ratio_5  = vols[-1] / avg_vol_5  if avg_vol_5  > 0 else 1.0
    vol_ratio_20 = vols[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
    vol_trend = (avg_vol_5 - avg_vol_20) / avg_vol_20 if avg_vol_20 > 0 else 0.0

    # ── Паттерн свечей ────────────────────────────────────────
    body = abs(closes[-1] - opens[-1])
    body_ratio   = body / hl if hl > 0 else 0.0
    upper_shadow = (highs[-1] - max(closes[-1], opens[-1])) / hl if hl > 0 else 0.0
    lower_shadow = (min(closes[-1], opens[-1]) - lows[-1]) / hl if hl > 0 else 0.0

    # ── Спайк ─────────────────────────────────────────────────
    spike_bps = price_change_1
    spike_direction = 1.0 if spike_bps > 0 else -1.0

    # ── RSI(14) ───────────────────────────────────────────────
    rsi = _calc_rsi(closes, 14)

    # ── Позиция цены ──────────────────────────────────────────
    high20 = max(highs[-20:])
    low20  = min(lows[-20:])
    rng20  = high20 - low20
    price_vs_high20 = (high20 - c) / rng20 if rng20 > 0 else 0.5
    price_vs_low20  = (c - low20) / rng20  if rng20 > 0 else 0.5

    vec = np.array([
        price_change_1, price_change_5, price_change_20,
        atr_14, atr_5, high_low_range,
        vol_ratio_5, vol_ratio_20, vol_trend,
        body_ratio, upper_shadow, lower_shadow,
        spike_bps, spike_direction,
        rsi,
        price_vs_high20, price_vs_low20,
        ob_imbalance,
    ], dtype=np.float32)

    # Заменяем inf/nan на 0
    vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
    return vec


def build_spot_features(
    candles: list[dict],
    spread_bps: float = 0.0,
    ob_imbalance: float = 0.5,
    ask_depth: float = 0.0,
    bid_depth: float = 0.0,
    trades_per_min: float = 0.0,
) -> np.ndarray | None:
    """Строит вектор фичей SPOT_FEATURE_DIM=14 для спотовой модели."""
    if len(candles) < 21:
        return None

    closes = [_safe(c["close"]) for c in candles]
    highs  = [_safe(c["high"])  for c in candles]
    lows   = [_safe(c["low"])   for c in candles]
    vols   = [_safe(c["volume"]) for c in candles]
    opens  = [_safe(c["open"])  for c in candles]

    c = closes[-1]
    if c == 0:
        return None

    price_change_1 = (closes[-1] - closes[-2]) / closes[-2] * 10000 if closes[-2] else 0.0
    price_change_5 = (closes[-1] - closes[-6]) / closes[-6] * 10000 if closes[-6] else 0.0

    avg_vol_5 = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else 1.0
    vol_ratio_5 = vols[-1] / avg_vol_5 if avg_vol_5 > 0 else 1.0

    atr_14 = _calc_atr_norm(highs, lows, closes, 14)
    rsi = _calc_rsi(closes, 14)

    hl = highs[-1] - lows[-1]
    body = abs(closes[-1] - opens[-1])
    body_ratio = body / hl if hl > 0 else 0.0

    high20 = max(highs[-20:])
    low20  = min(lows[-20:])
    rng20  = high20 - low20
    price_vs_high20 = (high20 - c) / rng20 if rng20 > 0 else 0.5
    price_vs_low20  = (c - low20) / rng20  if rng20 > 0 else 0.5

    vec = np.array([
        spread_bps, ob_imbalance, trades_per_min,
        price_change_1, price_change_5,
        vol_ratio_5, atr_14, body_ratio, rsi,
        price_vs_high20, price_vs_low20,
        ob_imbalance,
        ask_depth, bid_depth,
    ], dtype=np.float32)

    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def load_candles_from_db(
    symbol: str,
    category: str = "linear",
    interval: str = "1",
    limit: int = 500,
) -> list[dict]:
    """Загружает свечи из price_history для построения фичей."""
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT open, high, low, close, volume
                FROM price_history
                WHERE symbol=? AND category=? AND interval=?
                ORDER BY open_time_ms DESC LIMIT ?
                """,
                (symbol, category, interval, limit),
            ).fetchall()
        candles = [
            {"open": r[0], "high": r[1], "low": r[2], "close": r[3], "volume": r[4]}
            for r in reversed(rows)
        ]
        return candles
    except Exception as exc:
        log.warning("load_candles_from_db error: %s", exc)
        return []
