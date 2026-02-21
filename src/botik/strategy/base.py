"""
Базовый класс стратегии: возвращает intents (намерения выставить/снять ордера).
Стратегия не отправляет ордера сама — только intents -> RiskManager -> execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.botik.risk.manager import OrderIntent

if TYPE_CHECKING:
    from src.botik.state.state import TradingState


class BaseStrategy(ABC):
    @abstractmethod
    def get_intents(self, state: "TradingState") -> list[OrderIntent]:
        """
        На основе состояния стаканов и флага paused вернуть список намерений.
        При state.paused стратегия должна возвращать пустой список (или только отмены).
        """
        ...
