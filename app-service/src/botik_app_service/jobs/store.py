from datetime import datetime, timezone
from typing import Any

from botik_app_service.contracts.jobs import JobDetails


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobDetails] = {}

    def create(self, details: JobDetails) -> JobDetails:
        self._jobs[details.job_id] = details
        return details

    def update(self, job_id: str, **changes: Any) -> JobDetails:
        current = self._jobs[job_id]
        updated = current.model_copy(
            update={
                **changes,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._jobs[job_id] = updated
        return updated

    def get(self, job_id: str) -> JobDetails | None:
        return self._jobs.get(job_id)

    def list(self) -> list[JobDetails]:
        return sorted(self._jobs.values(), key=lambda item: item.updated_at, reverse=True)
