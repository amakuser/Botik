"""
RiskManager: жёсткие лимиты. Каждый ордер должен проходить через check_order.
Лимиты: initial_equity, max_total_exposure_pct, max_symbol_exposure_pct, max_orders_per_minute.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.botik.config import AppConfig, RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    """Намерение выставить ордер (до проверки риска)."""
    symbol: str
    side: str
    price: float
    qty: float
    order_link_id: str
    profile_id: str | None = None
    model_version: str | None = None
    action_entry_tick_offset: int | None = None
    action_order_qty_base: float | None = None
    action_target_profit: float | None = None
    action_safety_buffer: float | None = None
    action_min_top_book_qty: float | None = None
    action_stop_loss_pct: float | None = None
    action_take_profit_pct: float | None = None
    action_hold_timeout_sec: int | None = None
    action_maker_only: bool | None = None


@dataclass
class RiskCheckResult:
    allowed: bool
    reason: str


class RiskManager:
    """
    Проверка лимитов перед отправкой ордера.
    Хранит: initial_equity, лимиты в %, счётчик ордеров за последнюю минуту.
    Текущая экспозиция передаётся снаружи (сумма по открытым ордерам).
    """

    def __init__(self, risk_config: RiskConfig) -> None:
        self.initial_equity = risk_config.initial_equity_usdt
        self.max_total_pct = risk_config.max_total_exposure_pct_of_initial
        self.max_symbol_exposure_pct = risk_config.max_symbol_exposure_pct
        self.max_orders_per_minute = risk_config.max_orders_per_minute
        self.max_open_positions = int(risk_config.max_open_positions)
        self._order_timestamps: deque[float] = deque()

    def _max_total_exposure_usdt(self) -> float:
        return self.initial_equity * (self.max_total_pct / 100.0)

    def _max_symbol_exposure_usdt(self) -> float:
        return self.initial_equity * (self.max_symbol_exposure_pct / 100.0)

    def register_order_placed(self) -> None:
        """Вызвать после успешной отправки ордера (для лимита orders_per_minute)."""
        now = time.monotonic()
        self._order_timestamps.append(now)
        # Оставляем только последнюю минуту
        while self._order_timestamps and now - self._order_timestamps[0] > 60.0:
            self._order_timestamps.popleft()

    def _orders_in_last_minute(self) -> int:
        now = time.monotonic()
        while self._order_timestamps and now - self._order_timestamps[0] > 60.0:
            self._order_timestamps.popleft()
        return len(self._order_timestamps)

    def check_order(
        self,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        current_total_exposure_usdt: float,
        current_symbol_exposure_usdt: float,
        current_open_positions: int = 0,
    ) -> RiskCheckResult:
        """
        Проверить, можно ли выставить ордер. Экспозиция — сумма notional (price*qty)
        по уже открытым ордерам (total и по символу).
        current_open_positions — кол-во символов с открытой позицией прямо сейчас.
        """
        notional = price * qty
        if notional <= 0:
            return RiskCheckResult(False, "notional <= 0")

        if self._orders_in_last_minute() >= self.max_orders_per_minute:
            return RiskCheckResult(False, "max_orders_per_minute exceeded")

        # Hard cap on simultaneous open positions to prevent loss accumulation
        if self.max_open_positions > 0 and current_open_positions >= self.max_open_positions:
            return RiskCheckResult(
                False,
                f"max_open_positions reached ({current_open_positions}/{self.max_open_positions})",
            )

        new_total = current_total_exposure_usdt + notional
        if new_total > self._max_total_exposure_usdt():
            return RiskCheckResult(
                False,
                f"total_exposure would exceed limit ({new_total:.2f} > {self._max_total_exposure_usdt():.2f})",
            )

        new_symbol = current_symbol_exposure_usdt + notional
        max_sym = self._max_symbol_exposure_usdt()
        if new_symbol > max_sym:
            return RiskCheckResult(
                False,
                f"symbol_exposure would exceed limit ({new_symbol:.2f} > {max_sym:.2f})",
            )

        return RiskCheckResult(True, "OK")

