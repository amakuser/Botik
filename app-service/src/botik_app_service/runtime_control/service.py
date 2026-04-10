from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from botik_app_service.contracts.runtime_status import RuntimeId
from botik_app_service.jobs.process_adapter import ProcessAdapter
from botik_app_service.runtime_control.interfaces import RuntimeCommandSpec, RuntimeControlMode
from botik_app_service.runtime_status.interfaces import RuntimeActivity, RuntimeObservation

RUNTIME_LABELS: dict[RuntimeId, str] = {
    "spot": "Spot Runtime",
    "futures": "Futures Runtime",
}


@dataclass(slots=True)
class ManagedRuntime:
    runtime_id: RuntimeId
    process: Any
    control_file: Path
    mode: str
    last_heartbeat_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[None] | None = None
    stop_requested: bool = False


class RuntimeControlService:
    def __init__(
        self,
        *,
        repo_root: Path,
        process_adapter: ProcessAdapter,
        mode: RuntimeControlMode = "auto",
        runtime_status_fixture_path: Path | None = None,
        artifacts_dir: Path | None = None,
        heartbeat_interval_seconds: float = 1.0,
        stop_timeout_seconds: float = 8.0,
    ) -> None:
        self._repo_root = repo_root
        self._process_adapter = process_adapter
        self._mode = mode
        self._runtime_status_fixture_path = runtime_status_fixture_path
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._stop_timeout_seconds = stop_timeout_seconds
        state_root = artifacts_dir / "state" if artifacts_dir else repo_root / ".artifacts" / "local" / "state"
        self._control_dir = state_root / "runtime-control"
        self._control_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[RuntimeId, ManagedRuntime] = {}

    async def start(self, runtime_id: RuntimeId) -> None:
        current = self._runs.get(runtime_id)
        if current and self._process_adapter.poll(current.process) is None:
            return
        if current is not None:
            await self._finalize_run(current)

        spec = self._build_command(runtime_id)
        process = self._process_adapter.start(spec.command, cwd=spec.cwd, env=spec.env)
        now = datetime.now(UTC)
        run = ManagedRuntime(
            runtime_id=runtime_id,
            process=process,
            control_file=spec.control_file,
            mode=spec.mode,
            last_heartbeat_at=now,
        )
        self._runs[runtime_id] = run
        run.stdout_task = asyncio.create_task(self._consume_stream(run, process.stdout, level="INFO"))
        run.stderr_task = asyncio.create_task(self._consume_stream(run, process.stderr, level="ERROR"))
        run.wait_task = asyncio.create_task(self._wait_for_completion(run))

    async def stop(self, runtime_id: RuntimeId) -> None:
        run = self._runs.get(runtime_id)
        if run is None:
            return

        run.stop_requested = True
        run.control_file.parent.mkdir(parents=True, exist_ok=True)
        run.control_file.write_text("stop", encoding="utf-8")

        if run.wait_task is not None:
            try:
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)
                return
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._process_adapter.stop(run.process)

        if run.wait_task is not None:
            try:
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)
                return
            except asyncio.TimeoutError:
                self._process_adapter.kill_tree(run.process.pid)
                await asyncio.wait_for(run.wait_task, timeout=self._stop_timeout_seconds)

    async def shutdown(self) -> None:
        for runtime_id in list(self._runs):
            with contextlib.suppress(Exception):
                await self.stop(runtime_id)
        for run in list(self._runs.values()):
            await self._finalize_run(run)

    def observations(self) -> dict[RuntimeId, RuntimeObservation]:
        observations: dict[RuntimeId, RuntimeObservation] = {}
        for runtime_id, run in list(self._runs.items()):
            if self._process_adapter.poll(run.process) is not None:
                continue
            observations[runtime_id] = RuntimeObservation(
                runtime_id=runtime_id,
                label=RUNTIME_LABELS[runtime_id],
                pids=[int(run.process.pid)],
                activity=RuntimeActivity(
                    last_heartbeat_at=run.last_heartbeat_at,
                    last_error=run.last_error,
                    last_error_at=run.last_error_at,
                ),
            )
        return observations

    def _build_command(self, runtime_id: RuntimeId) -> RuntimeCommandSpec:
        control_file = self._control_dir / f"{runtime_id}.stop"
        with contextlib.suppress(FileNotFoundError):
            control_file.unlink()

        resolved_mode = self._resolve_mode()
        worker_mode = "fixture" if resolved_mode == "fixture" else "legacy"
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        command = [
            sys.executable,
            "-u",
            "-m",
            "botik_app_service.runtime.managed_runtime_worker",
            "--runtime-id",
            runtime_id,
            "--mode",
            worker_mode,
            "--control-file",
            str(control_file),
            "--heartbeat-interval",
            str(self._heartbeat_interval_seconds),
        ]
        return RuntimeCommandSpec(
            command=command,
            cwd=str(self._repo_root),
            env=env,
            control_file=control_file,
            mode=worker_mode,
        )

    def _resolve_mode(self) -> Literal["fixture", "compatibility"]:
        if self._mode == "fixture":
            return "fixture"
        if self._mode == "compatibility":
            return "compatibility"
        return "fixture" if self._runtime_status_fixture_path else "compatibility"

    async def _consume_stream(self, run: ManagedRuntime, stream: TextIO | None, *, level: str) -> None:
        if stream is None:
            return

        while True:
            line = await asyncio.to_thread(stream.readline)
            if not line:
                break
            await self._handle_line(run, line.strip(), level)

    async def _handle_line(self, run: ManagedRuntime, line: str, level: str) -> None:
        if not line:
            return

        if level == "ERROR":
            run.last_error = line
            run.last_error_at = datetime.now(UTC)
            return

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        payload_type = payload.get("type")
        if payload_type == "heartbeat":
            run.last_heartbeat_at = self._parse_timestamp(payload.get("timestamp")) or datetime.now(UTC)
            return

        if payload_type == "log":
            message = str(payload.get("message", ""))
            payload_level = str(payload.get("level", level)).upper()
            if payload_level in {"ERROR", "WARNING"}:
                run.last_error = message
                run.last_error_at = self._parse_timestamp(payload.get("timestamp")) or datetime.now(UTC)

    async def _wait_for_completion(self, run: ManagedRuntime) -> None:
        try:
            await asyncio.to_thread(run.process.wait)
            await asyncio.gather(
                *(task for task in [run.stdout_task, run.stderr_task] if task is not None),
                return_exceptions=True,
            )
        finally:
            await self._finalize_run(run)

    async def _finalize_run(self, run: ManagedRuntime) -> None:
        self._runs.pop(run.runtime_id, None)
        with contextlib.suppress(FileNotFoundError):
            run.control_file.unlink()
        await asyncio.sleep(0)

    @staticmethod
    def _parse_timestamp(raw: object) -> datetime | None:
        if raw is None:
            return None
        value = str(raw)
        try:
            if value.endswith("Z"):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
