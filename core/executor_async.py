# -*- coding: utf-8 -*-
"""
Асинхронный исполнитель (Python): asyncio.

Заглушка цикла. Полноценно: подписка на Bybit WS в той же петле, вызов
strategy.on_tick() и order_manager.apply_signal() по приходу данных.
"""
import asyncio
import logging
from typing import Any, List

from strategies.base import BaseStrategy, market_data

from core.executor import BaseExecutor

log = logging.getLogger("AsyncExecutor")


class AsyncExecutor(BaseExecutor):
    """Режим asyncio: цикл в одной петле; WS и стратегии можно подключить по аналогии с SyncExecutor."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._task: asyncio.Task | None = None

    def run(self) -> None:
        asyncio.run(self._run_loop())

    async def _run_loop(self) -> None:
        log.info("AsyncExecutor started")
        while not self._stopped:
            # Заглушка: здесь — подписка на Bybit WS и вызов стратегий по market_data
            await asyncio.sleep(1.0)
        log.info("AsyncExecutor stopped")

    def stop(self) -> None:
        super().stop()
        if self._task and not self._task.done():
            self._task.cancel()
