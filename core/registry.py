# -*- coding: utf-8 -*-
"""
Реестр стратегий: имя -> класс (Python).

Добавление новой стратегии: класс в strategies/, вызов registry.register("Name", MyStrategy)
и запись в config.yaml в списке strategies. Ядро не меняется.
"""
from typing import Type, TypeVar

from strategies.base import BaseStrategy

T = TypeVar("T", bound=BaseStrategy)


class StrategyRegistry:
    """Словарь имя стратегии -> класс для создания экземпляров из конфига."""

    def __init__(self) -> None:
        self._registry: dict[str, Type[BaseStrategy]] = {}

    def register(self, name: str, strategy_class: Type[T]) -> None:
        """Зарегистрировать класс под именем name."""
        self._registry[name] = strategy_class

    def get(self, name: str) -> Type[BaseStrategy]:
        """Вернуть класс стратегии по имени."""
        if name not in self._registry:
            raise KeyError(f"Strategy not registered: {name}")
        return self._registry[name]

    def __contains__(self, name: str) -> bool:
        return name in self._registry
