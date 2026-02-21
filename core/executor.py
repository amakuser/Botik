# -*- coding: utf-8 -*-
"""
Абстракция исполнителя (Python): синхронный и асинхронный режимы.

execution_mode в конфиге: "sync" — один поток, очередь из WebSocket;
"async" — asyncio (заглушка цикла, WebSocket можно подключить по аналогии с sync).
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, List

from strategies.base import BaseStrategy

log = logging.getLogger("Executor")


class BaseExecutor(ABC):
    """Общий интерфейс: run() — основной цикл, stop() — остановка."""

    def __init__(
        self,
        strategies: List[BaseStrategy],
        order_manager: Any,
        config: dict[str, Any],
    ) -> None:
        self.strategies = strategies
        self.order_manager = order_manager
        self.config = config
        self._stopped = False

    @abstractmethod
    def run(self) -> None:
        """Запуск цикла (блокирующий для sync)."""
        pass

    def stop(self) -> None:
        self._stopped = True


def get_executor(
    mode: str,
    strategies: List[BaseStrategy],
    order_manager: Any,
    config: dict[str, Any],
) -> BaseExecutor:
    """Вернуть SyncExecutor или AsyncExecutor в зависимости от execution_mode."""
    if mode == "async":
        from core.executor_async import AsyncExecutor
        return AsyncExecutor(strategies, order_manager, config)
    from core.executor_sync import SyncExecutor
    return SyncExecutor(strategies, order_manager, config)
