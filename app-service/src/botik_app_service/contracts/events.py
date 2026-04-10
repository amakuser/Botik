from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .jobs import JobState


class SystemEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: Literal["system"] = "system"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JobEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: Literal["job"] = "job"
    job_id: str
    job_type: str
    state: JobState
    progress: float = 0.0
    message: str | None = None


class LogEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: Literal["log"] = "log"
    job_id: str | None = None
    level: str
    message: str
