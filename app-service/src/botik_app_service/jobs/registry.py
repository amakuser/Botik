from botik_app_service.jobs.interfaces import JobDefinition


class JobRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, JobDefinition] = {}

    def register(self, definition: JobDefinition) -> None:
        self._definitions[definition.job_type] = definition

    def get(self, job_type: str) -> JobDefinition | None:
        return self._definitions.get(job_type)

    def list_definitions(self) -> list[JobDefinition]:
        return sorted(self._definitions.values(), key=lambda item: item.job_type)
