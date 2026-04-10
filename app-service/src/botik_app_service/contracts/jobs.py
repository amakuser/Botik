from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobState(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


class JobSummary(BaseModel):
    job_id: str
    job_type: str
    state: JobState
    progress: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JobDetails(BaseModel):
    job_id: str
    job_type: str
    state: JobState
    progress: float = 0.0
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exit_code: int | None = None
    last_error: str | None = None
    log_stream_id: str | None = None


class EmptyJobPayload(BaseModel):
    pass


class SampleDataImportJobPayload(BaseModel):
    sleep_ms: int = Field(default=80, ge=20, le=1_000)


class DataBackfillJobPayload(BaseModel):
    symbol: Literal["BTCUSDT"] = "BTCUSDT"
    category: Literal["spot"] = "spot"
    intervals: tuple[Literal["1m"]] = ("1m",)


class StartJobRequest(BaseModel):
    job_type: str
    payload: SampleDataImportJobPayload | DataBackfillJobPayload | EmptyJobPayload = Field(default_factory=EmptyJobPayload)

    def payload_dict(self) -> dict[str, Any]:
        return self.payload.model_dump()


class StopJobRequest(BaseModel):
    reason: str | None = None


def details_to_summary(details: JobDetails) -> JobSummary:
    return JobSummary(
        job_id=details.job_id,
        job_type=details.job_type,
        state=details.state,
        progress=details.progress,
        updated_at=details.updated_at,
    )
