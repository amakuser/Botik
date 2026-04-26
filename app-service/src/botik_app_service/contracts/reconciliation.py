from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ReconciliationState = Literal["healthy", "degraded", "stale", "failed", "unsupported"]


class ReconciliationSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_mode: Literal["resolved", "fixture"]
    state: ReconciliationState
    last_run_at: datetime | None = None
    last_run_finished_at: datetime | None = None
    last_run_status: str | None = None
    last_run_age_seconds: float | None = None
    next_run_in_seconds: int | None = None
    drift_count: int = 0
    staleness_threshold_hours: int = 24
    notes: list[str] = Field(default_factory=list)
