from datetime import datetime, timezone
from uuid import uuid4

from botik_app_service.contracts.events import JobEvent, LogEvent
from botik_app_service.contracts.jobs import JobDetails, JobState, StartJobRequest, StopJobRequest, details_to_summary
from botik_app_service.jobs.event_publisher import EventPublisher
from botik_app_service.jobs.interfaces import JobDefinition
from botik_app_service.jobs.registry import JobRegistry
from botik_app_service.jobs.store import JobStore
from botik_app_service.jobs.supervisor import JobSupervisor


class UnknownJobTypeError(ValueError):
    pass


class JobNotFoundError(ValueError):
    pass


class JobManager:
    def __init__(
        self,
        registry: JobRegistry,
        store: JobStore,
        supervisor: JobSupervisor,
        publisher: EventPublisher,
    ) -> None:
        self._registry = registry
        self._store = store
        self._supervisor = supervisor
        self._publisher = publisher

    def list(self) -> list[JobDetails]:
        return self._store.list()

    def get(self, job_id: str) -> JobDetails:
        details = self._store.get(job_id)
        if details is None:
            raise JobNotFoundError(job_id)
        return details

    async def start(self, request: StartJobRequest) -> JobDetails:
        definition = self._registry.get(request.job_type)
        if definition is None:
            raise UnknownJobTypeError(request.job_type)
        details = JobDetails(
            job_id=str(uuid4()),
            job_type=definition.job_type,
            state=JobState.QUEUED,
            progress=0.0,
            started_at=None,
            updated_at=datetime.now(timezone.utc),
            exit_code=None,
            last_error=None,
            log_stream_id=str(uuid4()),
        )
        self._store.create(details)
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=details.job_id,
                job_type=details.job_type,
                state=details.state,
                progress=details.progress,
            )
        )
        spawned = await self._supervisor.spawn(definition, request, details)
        updated = self._store.update(
            spawned.job_id,
            state=spawned.state,
            started_at=spawned.started_at,
            progress=spawned.progress,
        )
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=updated.job_id,
                job_type=updated.job_type,
                state=updated.state,
                progress=updated.progress,
            )
        )
        await self._publisher.publish_log_event(
            LogEvent(job_id=updated.job_id, level="INFO", message=f"Job {updated.job_type} accepted by skeleton.")
        )
        return updated

    async def stop(self, job_id: str, request: StopJobRequest) -> JobDetails:
        details = self.get(job_id)
        stopped = await self._supervisor.terminate(details, request)
        updated = self._store.update(
            stopped.job_id,
            state=stopped.state,
            exit_code=stopped.exit_code,
            last_error=stopped.last_error,
            progress=stopped.progress,
        )
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=updated.job_id,
                job_type=updated.job_type,
                state=updated.state,
                progress=updated.progress,
            )
        )
        return updated

    async def shutdown(self) -> None:
        for details in list(self._store.list()):
            if details.state in {JobState.QUEUED, JobState.STARTING, JobState.RUNNING, JobState.STOPPING}:
                await self.stop(details.job_id, StopJobRequest(reason="app-shutdown"))

    def list_summaries(self):
        return [details_to_summary(item) for item in self._store.list()]
