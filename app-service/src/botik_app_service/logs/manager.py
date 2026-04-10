import asyncio
import contextlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import AsyncIterator

from botik_app_service.contracts.logs import LogChannel, LogChannelSnapshot, LogEntry, LogStreamEvent
from botik_app_service.jobs.event_publisher import EventPublisher
from botik_app_service.logs.file_tail import FileTail
from botik_app_service.logs.legacy_adapter import build_legacy_runtime_source


@dataclass
class ChannelState:
    metadata: LogChannel
    entries: deque[LogEntry]
    subscribers: set[asyncio.Queue[dict]] = field(default_factory=set)
    lock: Lock = field(default_factory=Lock)


class LogCaptureHandler(logging.Handler):
    def __init__(self, manager: "LogsManager", channel: str) -> None:
        super().__init__()
        self._manager = manager
        self._channel = channel

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = "Failed to format log record."

        self._manager.publish(
            LogEntry(
                timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc),
                channel=self._channel,
                level=record.levelname,
                message=message,
                source=record.name,
            )
        )


class LogsManager:
    def __init__(
        self,
        *,
        buffer_size: int,
        snapshot_limit: int,
        artifacts_dir: Path | None = None,
        legacy_runtime_log_path: Path | None = None,
    ) -> None:
        self._buffer_size = buffer_size
        self._snapshot_limit = snapshot_limit
        self._artifacts_dir = artifacts_dir
        self._legacy_runtime_log_path = legacy_runtime_log_path
        self._channels: dict[str, ChannelState] = {}
        self._channel_order: list[str] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task[None]] = []

        self.register_channel("app", label="App Service", source_kind="memory", available=True)
        self.register_channel("jobs", label="Job Events", source_kind="events", available=True)
        self.register_channel("desktop", label="Desktop Shell", source_kind="file", available=False)
        if self._legacy_runtime_log_path is not None:
            self.register_channel("legacy-runtime", label="Legacy Runtime", source_kind="compatibility", available=False)

    def register_channel(self, channel_id: str, *, label: str, source_kind: str, available: bool) -> None:
        if channel_id in self._channels:
            return

        state = ChannelState(
            metadata=LogChannel(channel_id=channel_id, label=label, source_kind=source_kind, available=available),
            entries=deque(maxlen=self._buffer_size),
        )
        self._channels[channel_id] = state
        self._channel_order.append(channel_id)

    def create_capture_handler(self, channel: str = "app") -> logging.Handler:
        return LogCaptureHandler(self, channel)

    async def start(self, publisher: EventPublisher) -> None:
        self._loop = asyncio.get_running_loop()
        self._tasks.append(asyncio.create_task(self._bridge_job_logs(publisher), name="logs-bridge-jobs"))

        desktop_events_path = self._desktop_events_path()
        if desktop_events_path is not None:
            self._tasks.append(
                asyncio.create_task(
                    FileTail(
                        path=desktop_events_path,
                        parser=self._parse_desktop_event_line,
                        on_entry=self.publish,
                        on_available=lambda available: self.set_channel_availability("desktop", available),
                    ).run(),
                    name="logs-tail-desktop",
                )
            )

        if self._legacy_runtime_log_path is not None:
            legacy_source = build_legacy_runtime_source(self._legacy_runtime_log_path)
            self._tasks.append(
                asyncio.create_task(
                    FileTail(
                        path=legacy_source.path,
                        parser=legacy_source.parser,
                        on_entry=self.publish,
                        on_available=lambda available: self.set_channel_availability(legacy_source.channel_id, available),
                    ).run(),
                    name="logs-tail-legacy-runtime",
                )
            )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    def list_channels(self) -> list[LogChannel]:
        return [self._channels[channel_id].metadata.model_copy(deep=True) for channel_id in self._channel_order]

    def snapshot(self, channel_id: str) -> LogChannelSnapshot:
        state = self._require_channel(channel_id)
        with state.lock:
            available_entries = list(state.entries)
        entries = available_entries[-self._snapshot_limit :]
        return LogChannelSnapshot(channel=state.metadata.channel_id, entries=entries, truncated=len(available_entries) > len(entries))

    async def subscribe(self, channel_id: str) -> AsyncIterator[dict]:
        state = self._require_channel(channel_id)
        queue: asyncio.Queue[dict] = asyncio.Queue()
        with state.lock:
            state.subscribers.add(queue)
        try:
            while True:
                payload = await queue.get()
                yield payload
        finally:
            with state.lock:
                state.subscribers.discard(queue)

    def publish(self, entry: LogEntry) -> None:
        state = self._require_channel(entry.channel)
        payload = LogStreamEvent(channel=entry.channel, entry=entry).model_dump(mode="json")
        with state.lock:
            state.entries.append(entry)
            subscribers = list(state.subscribers)
        if self._loop is None:
            return
        for subscriber in subscribers:
            self._loop.call_soon_threadsafe(subscriber.put_nowait, payload)

    def set_channel_availability(self, channel_id: str, available: bool) -> None:
        state = self._require_channel(channel_id)
        state.metadata.available = available

    async def _bridge_job_logs(self, publisher: EventPublisher) -> None:
        async for payload in publisher.subscribe():
            if payload.get("kind") != "log":
                continue
            entry = LogEntry.model_validate(
                {
                    "timestamp": payload.get("timestamp"),
                    "channel": "jobs",
                    "level": payload.get("level", "INFO"),
                    "message": payload.get("message", ""),
                    "source": payload.get("job_id") or "job-manager",
                }
            )
            self.publish(entry)

    def _desktop_events_path(self) -> Path | None:
        if self._artifacts_dir is None:
            return None
        return self._artifacts_dir / "structured" / "service-events.jsonl"

    def _parse_desktop_event_line(self, line: str) -> LogEntry | None:
        stripped = line.strip()
        if not stripped:
            return None

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return LogEntry(channel="desktop", level="INFO", message=stripped, source="desktop-shell")

        kind = str(payload.get("kind", "desktop-event"))
        timestamp_raw = payload.get("timestamp")
        event_payload = payload.get("payload") or {}
        level = "INFO"
        if kind in {"shutdown_timeout", "shutdown_wait_error", "shutdown_request_failed"}:
            level = "WARNING"
        if kind in {"kill_fallback_completed"}:
            level = "ERROR"

        timestamp = datetime.now(timezone.utc)
        if isinstance(timestamp_raw, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp_raw / 1000, tz=timezone.utc)

        target = event_payload.get("target")
        if kind == "spawn_requested":
            message = f"spawn requested for {target or 'desktop component'}"
        elif kind == "spawned":
            message = f"spawned {target or 'desktop component'}"
        elif kind == "ready":
            message = f"ready: {target or 'desktop shell'}"
        elif kind == "shutdown_requested":
            message = "shutdown requested"
        elif kind == "shutdown_completed":
            message = "shutdown completed"
        elif kind == "shutdown_timeout":
            message = "shutdown timed out"
        elif kind == "kill_fallback_completed":
            message = "kill fallback completed"
        elif kind == "process_killed":
            message = f"process killed: {event_payload.get('pid', 'unknown')}"
        elif kind == "port_cleanup":
            message = f"port cleanup: {event_payload.get('port', 'unknown')}"
        else:
            message = kind

        return LogEntry(
            timestamp=timestamp,
            channel="desktop",
            level=level,
            message=message,
            source="desktop-shell",
        )

    def _require_channel(self, channel_id: str) -> ChannelState:
        try:
            return self._channels[channel_id]
        except KeyError as exc:
            raise KeyError(f"Unknown log channel: {channel_id}") from exc
