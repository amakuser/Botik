from dataclasses import dataclass
from typing import Any, Callable, Protocol

from botik_app_service.contracts.jobs import JobDetails, StartJobRequest, StopJobRequest


@dataclass(slots=True)
class JobLaunchSpec:
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None


@dataclass(slots=True)
class JobDefinition:
    job_type: str
    description: str
    launcher: Callable[[StartJobRequest, JobDetails], JobLaunchSpec] | None = None


class JobRegistryProtocol(Protocol):
    def get(self, job_type: str) -> JobDefinition | None: ...

    def list_definitions(self) -> list[JobDefinition]: ...


class JobStoreProtocol(Protocol):
    def create(self, details: JobDetails) -> JobDetails: ...

    def update(self, job_id: str, **changes: Any) -> JobDetails: ...

    def get(self, job_id: str) -> JobDetails | None: ...

    def list(self) -> list[JobDetails]: ...


class JobSupervisorProtocol(Protocol):
    async def spawn(self, definition: JobDefinition, request: StartJobRequest, details: JobDetails) -> JobDetails: ...

    async def terminate(self, details: JobDetails, reason: StopJobRequest | None = None) -> JobDetails: ...

    async def cleanup(self, details: JobDetails) -> None: ...
