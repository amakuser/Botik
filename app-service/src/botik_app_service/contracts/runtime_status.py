from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


RuntimeId = Literal["spot", "futures"]
RuntimeState = Literal["running", "degraded", "offline", "unknown"]
RuntimeSourceMode = Literal["fixture", "compatibility"]


class RuntimeStatus(BaseModel):
    runtime_id: RuntimeId
    label: str
    state: RuntimeState
    pids: list[int] = Field(default_factory=list)
    pid_count: int = 0
    last_heartbeat_at: datetime | None = None
    last_heartbeat_age_seconds: float | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    status_reason: str
    source_mode: RuntimeSourceMode


class RuntimeStatusSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    runtimes: list[RuntimeStatus]
