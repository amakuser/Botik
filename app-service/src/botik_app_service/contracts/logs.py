from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


LogChannelId = Literal["app", "jobs", "desktop", "legacy-runtime"]
LogSourceKind = Literal["memory", "events", "file", "compatibility"]


class LogChannel(BaseModel):
    channel_id: LogChannelId
    label: str
    source_kind: LogSourceKind
    available: bool = False


class LogEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    channel: LogChannelId
    level: str
    message: str
    source: str


class LogChannelSnapshot(BaseModel):
    channel: LogChannelId
    entries: list[LogEntry]
    truncated: bool = False


class LogStreamEvent(BaseModel):
    type: Literal["log-entry"] = "log-entry"
    channel: LogChannelId
    entry: LogEntry
