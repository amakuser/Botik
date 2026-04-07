"""
BasePositionPolicy — абстрактный интерфейс управления позицией.

Каждая политика вызывается на каждом тике и решает что делать с позицией:
hold / close_all / close_partial / add / hedge

Добавление новой политики: унаследовать BasePositionPolicy, реализовать on_tick().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    """Снимок открытой позиции для принятия решения."""
    trade_id: str
    symbol: str
    side: str                  # 'long' | 'short'
    entry_price: float
    qty: float
    stop_loss: float
    take_profit: float
    mark_price: float          # текущая цена (обновляется каждый тик)
    opened_at_ms: int          # timestamp открытия (unix ms)
    partial_closed_qty: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def unrealized_pnl(self) -> float:
        size = self.qty - self.partial_closed_qty
        if self.side == "long":
            return (self.mark_price - self.entry_price) * size
        return (self.entry_price - self.mark_price) * size

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == "long":
            return (self.mark_price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - self.mark_price) / self.entry_price * 100


@dataclass
class PolicyAction:
    """Решение политики по позиции."""
    action: str                 # 'hold' | 'close_all' | 'close_partial' | 'add' | 'hedge'
    qty_pct: float = 1.0        # доля позиции (0.0–1.0), для close_partial / add
    reason: str = ""
    new_stop_loss: float | None = None   # если нужно сдвинуть SL
    new_take_profit: float | None = None


HOLD = PolicyAction(action="hold")


class BasePositionPolicy(ABC):
    """
    Базовый класс политики управления позицией.

    Жизненный цикл:
      1. on_open(position)  — вызывается при открытии позиции
      2. on_tick(position)  — вызывается на каждом тике с обновлённым mark_price
      3. on_close(position, action) — вызывается после закрытия

    Возвращаемый PolicyAction определяет что делает FuturesPaperEngine.
    """

    @abstractmethod
    def on_tick(self, position: Position) -> PolicyAction:
        """Основной метод. Вызывается на каждом тике."""
        ...

    def on_open(self, position: Position) -> None:
        """Хук при открытии позиции (опционально)."""

    def on_close(self, position: Position, action: PolicyAction) -> None:
        """Хук при закрытии позиции (опционально)."""
