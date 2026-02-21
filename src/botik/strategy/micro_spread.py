"""
Микро-спред: 0–2 post-only лимита на символ (bid/ask).
Выставлять только если spread >= min_spread_ticks; replace_interval_ms и TTL; контроль инвентаря.
При state.paused не шлём intents (только обновляем состояние / метрики снаружи).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from src.botik.risk.manager import OrderIntent
from src.botik.strategy.base import BaseStrategy

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState

logger = logging.getLogger(__name__)


class MicroSpreadStrategy(BaseStrategy):
    """
    До 2 ордеров на символ (один bid, один ask). PostOnly.
    Условия: spread >= min_spread_ticks; учёт replace_interval и order_ttl_sec.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._last_replace_time: dict[str, float] = {}
        self._order_link_ids: dict[str, tuple[str | None, str | None]] = {}  # symbol -> (bid_link_id, ask_link_id)

    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        if state.paused:
            return []
        intents: list[OrderIntent] = []
        now = time.monotonic()
        replace_interval_sec = self.config.strategy.replace_interval_ms / 1000.0
        min_spread = self.config.strategy.min_spread_ticks
        tick_size = self.config.strategy.default_tick_size
        # Размер котировки в базовой валюте (упрощённо — фиксированный лот для MVP)
        order_qty = 0.001  # минимальный разумный объём для теста

        for symbol in self.config.symbols:
            ob = state.get_orderbook(symbol)
            if ob is None:
                continue
            if ob.spread_ticks < min_spread:
                continue
            last = self._last_replace_time.get(symbol, 0)
            if now - last < replace_interval_sec:
                continue
            self._last_replace_time[symbol] = now
            bid_price = round(ob.best_bid / tick_size) * tick_size
            ask_price = round(ob.best_ask / tick_size) * tick_size
            bid_link = f"mm-{symbol}-bid-{uuid.uuid4().hex[:12]}"
            ask_link = f"mm-{symbol}-ask-{uuid.uuid4().hex[:12]}"
            intents.append(
                OrderIntent(symbol=symbol, side="Buy", price=bid_price, qty=order_qty, order_link_id=bid_link)
            )
            intents.append(
                OrderIntent(symbol=symbol, side="Sell", price=ask_price, qty=order_qty, order_link_id=ask_link)
            )
        return intents


# --- Как проверить: передать state с стаканом (spread_ticks >= 2), вызвать get_intents; при paused — пустой список.
# --- Частые ошибки: не округлять цену по tick_size; не учитывать replace_interval (слишком частые замены).
# --- Что улучшить позже: инвентарь (не выставлять bid если уже длинный); TTL отмена старых ордеров; размер ордера из конфига.
