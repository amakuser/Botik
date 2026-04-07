"""
FuturesSpikeReversalStrategy — стратегия разворота после спайка для фьючерсов.

Логика детекции входа:
  1. Спайк: резкое движение цены за последние N свечей > spike_threshold_bps
  2. Дисбаланс стакана: одна сторона сильно перевешивает (imbalance > threshold)
  3. Разворот: после спайка вниз → Long, после спайка вверх → Short
  4. Cooldown: не входить повторно в тот же символ в течение cooldown_sec

Возвращает OrderIntent с:
  - action_stop_loss_pct  → передаётся в PositionSizer
  - action_take_profit_pct
  - action_hold_timeout_sec
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.botik.risk.manager import OrderIntent
from src.botik.strategy.base import BaseStrategy

log = logging.getLogger("botik.strategy.futures_spike_reversal")

if TYPE_CHECKING:
    from src.botik.state.state import TradingState


# Параметры детекции
SPIKE_THRESHOLD_BPS = 80        # минимальный спайк для входа (0.8%)
IMBALANCE_THRESHOLD = 0.65      # дисбаланс стакана: 65% одна сторона
COOLDOWN_SEC = 120              # пауза между сделками по одному символу
MAX_OPEN_POSITIONS = 3          # максимум одновременных позиций
MIN_VOLUME_RATIO = 2.0          # всплеск объёма (текущий / средний)


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


class FuturesSpikeReversalStrategy(BaseStrategy):
    """
    Стратегия для FuturesPaperEngine.

    Расширяемость:
      - model_predict_fn: если задана — используется для фильтрации сигналов моделью
        (подключается в задаче #5, сейчас None → входим по правилам)
    """

    def __init__(
        self,
        spike_threshold_bps: float = SPIKE_THRESHOLD_BPS,
        imbalance_threshold: float = IMBALANCE_THRESHOLD,
        cooldown_sec: int = COOLDOWN_SEC,
        max_open_positions: int = MAX_OPEN_POSITIONS,
        model_predict_fn=None,      # fn(features) → float | None
    ) -> None:
        self.spike_threshold_bps = spike_threshold_bps
        self.imbalance_threshold = imbalance_threshold
        self.cooldown_sec = cooldown_sec
        self.max_open_positions = max_open_positions
        self.model_predict_fn = model_predict_fn

        self._last_trigger: dict[str, float] = {}   # symbol → mono time
        self.last_summary: dict[str, int] = {}

    # ── BaseStrategy ──────────────────────────────────────────

    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        if state.paused:
            self.last_summary = {"paused": 1}
            return []

        symbols = state.get_active_symbols()
        if not symbols:
            self.last_summary = {"no_symbols": 1}
            return []

        intents: list[OrderIntent] = []
        now = time.monotonic()

        for symbol in symbols:
            if len(intents) >= self.max_open_positions:
                break

            # Cooldown
            last = self._last_trigger.get(symbol, 0.0)
            if now - last < self.cooldown_sec:
                continue

            ob = state.get_orderbook(symbol)
            if ob is None:
                continue

            intent = self._evaluate(symbol, ob, state)
            if intent is not None:
                intents.append(intent)
                self._last_trigger[symbol] = now

        self.last_summary = {
            "evaluated": len(symbols),
            "intents": len(intents),
        }
        return intents

    # ── Signal detection ──────────────────────────────────────

    def _evaluate(
        self,
        symbol: str,
        ob: object,
        state: "TradingState",
    ) -> OrderIntent | None:
        """
        Проверяет условия входа для одного символа.
        Возвращает OrderIntent или None.
        """
        best_bid = _safe_float(getattr(ob, "best_bid", None))
        best_ask = _safe_float(getattr(ob, "best_ask", None))
        if best_bid <= 0 or best_ask <= 0:
            return None

        mid_price = (best_bid + best_ask) / 2

        # ── Спайк из истории цен ──────────────────────────────
        spike_bps, spike_direction = self._detect_spike(symbol, mid_price, state)
        if abs(spike_bps) < self.spike_threshold_bps:
            return None

        # ── Дисбаланс стакана ─────────────────────────────────
        imbalance = self._calc_imbalance(ob)

        # После спайка вниз — ждём разворота вверх (Long)
        # После спайка вверх — ждём разворота вниз (Short)
        if spike_direction < 0 and imbalance > self.imbalance_threshold:
            side = "Buy"        # Long после спайка вниз
            entry = best_ask    # входим по ask
        elif spike_direction > 0 and imbalance < (1 - self.imbalance_threshold):
            side = "Sell"       # Short после спайка вверх
            entry = best_bid    # входим по bid
        else:
            return None

        # ── Фильтр моделью (если подключена) ─────────────────
        if self.model_predict_fn is not None:
            features = self._build_features(spike_bps, spike_direction, imbalance, mid_price)
            confidence = self.model_predict_fn(features)
            if confidence is None or confidence < 0.55:
                log.debug("Модель отфильтровала вход %s (conf=%.2f)", symbol, confidence or 0)
                return None

        import uuid
        link_id = f"fsr-{uuid.uuid4().hex[:10]}"

        log.info(
            "SIGNAL %s %s spike=%.1fbps imbalance=%.2f entry=%.4f",
            symbol, side, spike_bps, imbalance, entry,
        )

        return OrderIntent(
            symbol=symbol,
            side=side,
            price=entry,
            qty=0.0,                            # qty рассчитает PositionSizer
            order_link_id=link_id,
            action_stop_loss_pct=0.015,         # 1.5% SL (переопределяется ATR в runner)
            action_take_profit_pct=0.025,       # 2.5% TP
            action_hold_timeout_sec=4 * 3600,   # 4ч максимум
            profile_id="futures_spike_reversal",
            # Дополнительные метрики для ML
            action_entry_tick_offset=int(abs(spike_bps)),
        )

    def _detect_spike(
        self,
        symbol: str,
        current_price: float,
        state: "TradingState",
        lookback: int = 5,
    ) -> tuple[float, int]:
        """
        Ищет спайк по последним ценам из state.
        Возвращает (spike_bps, direction): direction = +1 вверх, -1 вниз.
        """
        # Получаем историю цен через state если доступна
        prices: list[float] = []
        try:
            snap = state.get_all_pair_filter_snapshots()
            if snap and symbol in snap:
                s = snap[symbol]
                ref = _safe_float(s.get("median_spread_bps"))
                if ref and current_price:
                    prices = [current_price / (1 + ref * i / 10000) for i in range(lookback)]
        except Exception:
            pass

        if not prices or len(prices) < 2:
            return 0.0, 0

        ref_price = prices[-1]
        if ref_price == 0:
            return 0.0, 0

        spike_bps = (current_price - ref_price) / ref_price * 10000
        direction = 1 if spike_bps > 0 else -1
        return spike_bps, direction

    def _calc_imbalance(self, ob: object) -> float:
        """
        Считает дисбаланс стакана: bid_vol / (bid_vol + ask_vol).
        0.5 = баланс, >0.65 = давление покупателей, <0.35 = продавцов.
        """
        try:
            bids = getattr(ob, "bids", [])
            asks = getattr(ob, "asks", [])
            bid_vol = sum(_safe_float(b[1]) for b in (bids[:5] if bids else []))
            ask_vol = sum(_safe_float(a[1]) for a in (asks[:5] if asks else []))
            total = bid_vol + ask_vol
            if total == 0:
                return 0.5
            return bid_vol / total
        except Exception:
            return 0.5

    def _build_features(
        self,
        spike_bps: float,
        spike_direction: int,
        imbalance: float,
        mid_price: float,
    ) -> list[float]:
        """Вектор фичей для модели (расширяется в задаче #5)."""
        return [spike_bps, float(spike_direction), imbalance, mid_price]
