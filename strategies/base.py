# -*- coding: utf-8 -*-
"""
Базовый интерфейс стратегии и типы данных (Python).

Все стратегии наследуют BaseStrategy и реализуют on_tick(MarketData) -> Signal | None.
Параметры (периоды MA, размер позиции и т.д.) хранятся в params; ML может их обновлять.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Signal:
    """
    Сигнал на сделку для OrderManager.
    direction: "long" | "short"
    size: объём в базовой валюте (или контрактах)
    take_profit / stop_loss: опциональные уровни
    strategy_id: имя стратегии (для лимитов и статистики)
    """
    direction: str
    size: float
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    strategy_id: str = ""


@dataclass
class MarketData:
    """
    Снимок рынка для стратегии.
    extra: доп. данные (например fast_ma, slow_ma от executor).
    """
    symbol: str
    timeframe: str
    price: float
    timestamp: float
    extra: dict[str, Any]


class BaseStrategy(ABC):
    """
    Абстрактная стратегия. Реализации — в strategies/ (например MAStrategy).
    Конструктор: symbol, timeframe, params из конфига.
    """

    def __init__(self, symbol: str, timeframe: str, params: dict[str, Any]):
        self.symbol = symbol
        self.timeframe = timeframe
        self.params = params

    @abstractmethod
    def on_tick(self, market_data: MarketData) -> Optional[Signal]:
        """Обработать обновление рынка; вернуть сигнал или None."""
        pass

    def get_params(self) -> dict[str, Any]:
        """Текущие параметры (могут быть переопределены ML/правилами)."""
        return self.params
