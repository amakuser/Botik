import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TextIO

from botik_app_service.contracts.events import JobEvent, LogEvent
from botik_app_service.contracts.jobs import JobDetails, JobState, StartJobRequest, StopJobRequest
from botik_app_service.jobs.event_publisher import EventPublisher
from botik_app_service.jobs.interfaces import JobDefinition
from botik_app_service.jobs.process_adapter import ProcessAdapter
from botik_app_service.jobs.store import JobStore


@dataclass(slots=True)
class ManagedRun:
    job_id: str
    job_type: str
    process: Any
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[None] | None = None
    stop_requested: bool = False
    termination_reason: str | None = None


class JobSupervisor:
    def __init__(
        self,
        process_adapter: ProcessAdapter,
        store: JobStore,
        publisher: EventPublisher,
        stop_timeout_seconds: float = 5.0,
    ) -> None:
        self._process_adapter = process_adapter
        self._store = store
        self._publisher = publisher
        self._stop_timeout_seconds = stop_timeout_seconds
        self._runs: dict[str, ManagedRun] = {}

    async def spawn(self, definition: JobDefinition, request: StartJobRequest, details: JobDetails) -> JobDetails:
        if definition.launcher is None:
            raise ValueError(f"Job {definition.job_type} does not define a launcher.")

        starting = self._store.update(
            details.job_id,
            state=JobState.STARTING,
            started_at=datetime.now(timezone.utc),
            progress=0.0,
            exit_code=None,
            last_error=None,
        )
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=starting.job_id,
                job_type=starting.job_type,
                state=starting.state,
                progress=starting.progress,
                message="Starting worker process.",
            )
        )

        try:
            launch_spec = definition.launcher(request, starting)
            process = self._process_adapter.start(launch_spec.command, cwd=launch_spec.cwd, env=launch_spec.env)
        except Exception as exc:
            failed = self._store.update(
                details.job_id,
                state=JobState.FAILED,
                exit_code=-1,
                last_error=str(exc),
            )
            await self._publisher.publish_job_event(
                JobEvent(
                    job_id=failed.job_id,
                    job_type=failed.job_type,
                    state=failed.state,
                    progress=failed.progress,
                    message="Worker failed to start.",
                )
            )
            await self._publisher.publish_log_event(
                LogEvent(job_id=failed.job_id, level="ERROR", message=f"Failed to start worker: {exc}")
            )
            return failed

        run = ManagedRun(job_id=details.job_id, job_type=details.job_type, process=process)
        self._runs[details.job_id] = run
        run.stdout_task = asyncio.create_task(self._consume_stream(run, process.stdout, level="INFO"))
        run.stderr_task = asyncio.create_task(self._consume_stream(run, process.stderr, level="ERROR"))
        run.wait_task = asyncio.create_task(self._wait_for_completion(run))

        running = self._store.update(
            details.job_id,
            state=JobState.RUNNING,
            started_at=starting.started_at,
            progress=0.0,
        )
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=running.job_id,
                job_type=running.job_type,
                state=running.state,
                progress=running.progress,
                message="Worker is running.",
            )
        )
        await self._publisher.publish_log_event(
            LogEvent(job_id=running.job_id, level="INFO", message=f"Started job {running.job_type}.")
        )
        return running

    async def terminate(self, details: JobDetails, reason: StopJobRequest | None = None) -> JobDetails:
        run = self._runs.get(details.job_id)
        if run is None:
            return details

        run.stop_requested = True
        run.termination_reason = reason.reason if reason else None
        stopping = self._store.update(
            details.job_id,
            state=JobState.STOPPING,
        )
        await self._publisher.publish_job_event(
            JobEvent(
                job_id=stopping.job_id,
                job_type=stopping.job_type,
                state=stopping.state,
                progress=stopping.progress,
                message="Stop requested.",
            )
        )
        await self._publisher.publish_log_event(
            LogEvent(
                job_id=stopping.job_id,
                level="WARNING",
                message=f"Stop requested for {stopping.job_type}: {run.termination_reason or 'user-request'}",
            )
        )

        self._process_adapter.stop(run.process)
        if run.wait_task is not None:
            try:
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)
            except asyncio.TimeoutError:
                self._process_adapter.kill_tree(run.process.pid)
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)
        return self._store.get(details.job_id) or stopping

    async def cleanup(self, details: JobDetails) -> None:
        run = self._runs.get(details.job_id)
        if run is None:
            return

        self._process_adapter.kill_tree(run.process.pid)
        if run.wait_task is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)

    async def _consume_stream(self, run: ManagedRun, stream: TextIO | None, level: str) -> None:
        if stream is None:
            return

        while True:
            line = await asyncio.to_thread(stream.readline)
            if not line:
                break
            await self._handle_worker_line(run, line.strip(), level)

    async def _handle_worker_line(self, run: ManagedRun, line: str, level: str) -> None:
        if not line:
            return

        if level == "ERROR":
            await self._publisher.publish_log_event(LogEvent(job_id=run.job_id, level=level, message=line))
            return

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            await self._publisher.publish_log_event(LogEvent(job_id=run.job_id, level=level, message=line))
            return

        payload_type = payload.get("type")
        if payload_type == "progress":
            progress = max(0.0, min(float(payload.get("progress", 0.0)), 1.0))
            current = self._store.get(run.job_id)
            next_state = JobState.RUNNING
            if current is not None and current.state == JobState.STOPPING:
                next_state = JobState.STOPPING
            updated = self._store.update(run.job_id, progress=progress, state=next_state)
            await self._publisher.publish_job_event(
                JobEvent(
                    job_id=updated.job_id,
                    job_type=updated.job_type,
                    state=updated.state,
                    progress=updated.progress,
                    message=payload.get("message"),
                    phase=payload.get("phase"),
                    symbol=payload.get("symbol"),
                    category=payload.get("category"),
                    interval=payload.get("interval"),
                    completed_units=int(payload["completed_units"]) if payload.get("completed_units") is not None else None,
                    total_units=int(payload["total_units"]) if payload.get("total_units") is not None else None,
                    rows_written=int(payload["rows_written"]) if payload.get("rows_written") is not None else None,
                )
            )
            return

        if payload_type == "log":
            await self._publisher.publish_log_event(
                LogEvent(
                    job_id=run.job_id,
                    level=str(payload.get("level", level)).upper(),
                    message=str(payload.get("message", "")),
                )
            )
            return

        await self._publisher.publish_log_event(LogEvent(job_id=run.job_id, level=level, message=line))

    async def _wait_for_completion(self, run: ManagedRun) -> None:
        try:
            exit_code = await asyncio.to_thread(run.process.wait)
            await asyncio.gather(
                *(task for task in [run.stdout_task, run.stderr_task] if task is not None),
                return_exceptions=True,
            )
            current = self._store.get(run.job_id)
            if current is None:
                return

            if run.stop_requested:
                updated = self._store.update(
                    run.job_id,
                    state=JobState.CANCELLED,
                    exit_code=exit_code,
                    last_error=run.termination_reason,
                )
                await self._publisher.publish_job_event(
                    JobEvent(
                        job_id=updated.job_id,
                        job_type=updated.job_type,
                        state=updated.state,
                        progress=updated.progress,
                        message="Job stopped.",
                    )
                )
                await self._publisher.publish_log_event(
                    LogEvent(job_id=updated.job_id, level="WARNING", message=f"Job stopped with exit code {exit_code}.")
                )
                return

            if exit_code == 0:
                updated = self._store.update(
                    run.job_id,
                    state=JobState.COMPLETED,
                    progress=max(current.progress, 1.0),
                    exit_code=exit_code,
                    last_error=None,
                )
                await self._publisher.publish_job_event(
                    JobEvent(
                        job_id=updated.job_id,
                        job_type=updated.job_type,
                        state=updated.state,
                        progress=updated.progress,
                        message="Job completed.",
                    )
                )
                await self._publisher.publish_log_event(
                    LogEvent(job_id=updated.job_id, level="INFO", message="Job completed successfully.")
                )
                return

            updated = self._store.update(
                run.job_id,
                state=JobState.FAILED,
                exit_code=exit_code,
                last_error=f"Process exited with code {exit_code}",
            )
            await self._publisher.publish_job_event(
                JobEvent(
                    job_id=updated.job_id,
                    job_type=updated.job_type,
                    state=updated.state,
                    progress=updated.progress,
                    message="Job failed.",
                )
            )
            await self._publisher.publish_log_event(
                LogEvent(job_id=updated.job_id, level="ERROR", message=updated.last_error or "Unknown job failure.")
            )
        finally:
            self._runs.pop(run.job_id, None)
