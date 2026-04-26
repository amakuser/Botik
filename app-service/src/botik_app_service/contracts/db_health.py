from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


DbHealthState = Literal["ok", "degraded", "unavailable"]


class DbHealthSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: DbHealthState
    last_check_at: datetime
    latency_ms: float | None = None
    error: str | None = None
    db_path: str
    slow_threshold_ms: int
