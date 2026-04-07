"""
EventBus — реактивный event bus для pywebview-дашборда (T40).

Принцип работы:
  - Python-код в любом месте вызывает bus.emit(type, data)
  - EventDispatcher (фоновый поток) забирает события и вызывает
    window.evaluate_js("_onServerEvent(type, data)")
  - JS-обработчик _onServerEvent() обновляет UI без polling

Это заменяет part polling (логи, баланс, snapshot) на push-модель.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any

log = logging.getLogger("botik.event_bus")

# Сколько событий держим в очереди до сброса
_QUEUE_MAX = 500

# Как часто диспетчер смотрит в очередь (секунды)
_DISPATCH_INTERVAL = 0.15


class EventBus:
    """Thread-safe event queue.  Потокобезопасная очередь событий."""

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_QUEUE_MAX)

    def emit(self, event_type: str, data: Any) -> None:
        """Put an event on the queue.  Non-blocking; silently drops if full."""
        try:
            self._queue.put_nowait({"type": event_type, "data": data})
        except queue.Full:
            pass

    def drain(self) -> list[dict[str, Any]]:
        """Drain all pending events.  Returns empty list when queue is empty."""
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events


# Singleton bus — импортируется везде, где нужно слать события
bus: EventBus = EventBus()


class EventDispatcher:
    """
    Фоновый поток, который забирает события из шины и вызывает
    JS-функцию _onServerEvent() через window.evaluate_js().

    Требует вызова .attach_window(window) после создания pywebview-окна.
    """

    def __init__(self) -> None:
        self._window: Any | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="event-dispatch"
        )

    def start(self) -> None:
        self._thread.start()

    def attach_window(self, window: Any) -> None:
        self._window = window

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            events = bus.drain()
            if events:
                win = self._window
                if win is not None:
                    for ev in events:
                        try:
                            js = (
                                "_onServerEvent("
                                + json.dumps(ev["type"])
                                + ","
                                + json.dumps(ev["data"])
                                + ");"
                            )
                            win.evaluate_js(js)
                        except Exception as exc:
                            log.debug("[event_bus] evaluate_js failed: %s", exc)
            self._stop.wait(timeout=_DISPATCH_INTERVAL)
