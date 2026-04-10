from datetime import datetime, timezone

from botik_app_service.contracts.jobs import JobDetails, JobState, StartJobRequest, StopJobRequest
from botik_app_service.jobs.interfaces import JobDefinition
from botik_app_service.jobs.process_adapter import ProcessAdapter


class JobSupervisor:
    def __init__(self, process_adapter: ProcessAdapter) -> None:
        self._process_adapter = process_adapter

    async def spawn(self, definition: JobDefinition, request: StartJobRequest, details: JobDetails) -> JobDetails:
        del definition, request
        return details.model_copy(
            update={
                "state": JobState.STARTING,
                "started_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    async def terminate(self, details: JobDetails, reason: StopJobRequest | None = None) -> JobDetails:
        del reason
        return details.model_copy(
            update={
                "state": JobState.CANCELLED,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    async def cleanup(self, details: JobDetails) -> None:
        del details
