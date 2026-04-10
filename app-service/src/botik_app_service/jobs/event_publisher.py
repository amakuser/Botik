import asyncio
import json
from collections import deque
from typing import AsyncIterator

from botik_app_service.contracts.events import JobEvent, LogEvent, SystemEvent


class EventPublisher:
    def __init__(self, buffer_size: int = 32) -> None:
        self._recent = deque(maxlen=buffer_size)
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._stopped = asyncio.Event()

    async def publish_job_event(self, event: JobEvent) -> None:
        await self._publish(event.model_dump(mode="json"))

    async def publish_log_event(self, event: LogEvent) -> None:
        await self._publish(event.model_dump(mode="json"))

    async def publish_system_event(self, event: SystemEvent) -> None:
        await self._publish(event.model_dump(mode="json"))

    async def _publish(self, payload: dict) -> None:
        self._recent.append(payload)
        for subscriber in list(self._subscribers):
            await subscriber.put(payload)

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            for payload in list(self._recent):
                yield payload
            while not self._stopped.is_set():
                payload = await queue.get()
                yield payload
        finally:
            self._subscribers.discard(queue)

    async def run_heartbeat(self, interval_seconds: float) -> None:
        while not self._stopped.is_set():
            await self.publish_system_event(SystemEvent(message="heartbeat"))
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._stopped.set()

    @staticmethod
    def encode_sse(payload: dict) -> str:
        kind = payload.get("kind", "message")
        event_id = payload.get("event_id", "")
        data = json.dumps(payload, ensure_ascii=True)
        return f"event: {kind}\nid: {event_id}\ndata: {data}\n\n"
