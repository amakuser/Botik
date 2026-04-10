from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from botik_app_service.contracts.runtime_status import RuntimeId, RuntimeState, RuntimeStatus, RuntimeStatusSnapshot
from botik_app_service.runtime_status.interfaces import RuntimeActivity, RuntimeObservation, RuntimeObservationProvider
from botik_app_service.runtime_status.legacy_status_adapter import LegacyRuntimeStatusAdapter
from botik_app_service.runtime_status.process_probe import RuntimeProcessProbe

RUNTIME_LABELS: dict[RuntimeId, str] = {
    "spot": "Spot Runtime",
    "futures": "Futures Runtime",
}


class RuntimeStatusService:
    def __init__(
        self,
        repo_root: Path,
        heartbeat_stale_seconds: float,
        fixture_path: Path | None = None,
        process_probe: RuntimeProcessProbe | None = None,
        legacy_adapter: LegacyRuntimeStatusAdapter | None = None,
        observation_provider: RuntimeObservationProvider | None = None,
    ) -> None:
        self._heartbeat_stale_seconds = heartbeat_stale_seconds
        self._fixture_path = fixture_path
        self._process_probe = process_probe or RuntimeProcessProbe()
        self._legacy_adapter = legacy_adapter or LegacyRuntimeStatusAdapter(repo_root=repo_root)
        self._observation_provider = observation_provider

    def snapshot(self) -> RuntimeStatusSnapshot:
        observations = self._observation_provider.observations() if self._observation_provider is not None else {}
        if self._fixture_path:
            payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
            snapshot = RuntimeStatusSnapshot.model_validate(payload)
            return self._overlay_fixture_snapshot(snapshot, observations=observations, source_mode="fixture")

        now = datetime.now(UTC)
        processes = self._process_probe.scan()
        runtimes = [
            self._build_runtime_status(
                runtime_id=runtime_id,
                pids=processes[runtime_id],
                now=now,
                observation=observations.get(runtime_id),
            )
            for runtime_id in ("spot", "futures")
        ]
        return RuntimeStatusSnapshot(generated_at=now, runtimes=runtimes)

    def runtime_status(self, runtime_id: RuntimeId) -> RuntimeStatus:
        snapshot = self.snapshot()
        for runtime in snapshot.runtimes:
            if runtime.runtime_id == runtime_id:
                return runtime
        raise KeyError(runtime_id)

    def _build_runtime_status(
        self,
        runtime_id: RuntimeId,
        pids: list[int],
        now: datetime,
        observation: RuntimeObservation | None = None,
    ) -> RuntimeStatus:
        if observation is not None:
            return self._build_runtime_from_observation(observation=observation, now=now, source_mode="compatibility")

        activity = self._legacy_adapter.read_activity(runtime_id)
        state, reason, age_seconds = self._classify_status(pids=pids, activity=activity, now=now)
        return RuntimeStatus(
            runtime_id=runtime_id,
            label=RUNTIME_LABELS[runtime_id],
            state=state,
            pids=sorted(pids),
            pid_count=len(pids),
            last_heartbeat_at=activity.last_heartbeat_at,
            last_heartbeat_age_seconds=age_seconds,
            last_error=activity.last_error,
            last_error_at=activity.last_error_at,
            status_reason=reason,
            source_mode="compatibility",
        )

    def _overlay_fixture_snapshot(
        self,
        snapshot: RuntimeStatusSnapshot,
        *,
        observations: dict[RuntimeId, RuntimeObservation],
        source_mode: str,
    ) -> RuntimeStatusSnapshot:
        now = datetime.now(UTC)
        normalized = []
        for runtime in snapshot.runtimes:
            observation = observations.get(runtime.runtime_id)
            if observation is not None:
                normalized.append(self._build_runtime_from_observation(observation=observation, now=now, source_mode=source_mode))
            else:
                normalized.append(
                    runtime.model_copy(
                        update={
                            "pid_count": len(runtime.pids),
                            "source_mode": source_mode,
                        }
                    )
                )
        return RuntimeStatusSnapshot(generated_at=snapshot.generated_at, runtimes=normalized)

    def _build_runtime_from_observation(
        self,
        *,
        observation: RuntimeObservation,
        now: datetime,
        source_mode: str,
    ) -> RuntimeStatus:
        state, reason, age_seconds = self._classify_status(
            pids=observation.pids,
            activity=observation.activity,
            now=now,
        )
        return RuntimeStatus(
            runtime_id=observation.runtime_id,
            label=observation.label,
            state=state,
            pids=sorted(observation.pids),
            pid_count=len(observation.pids),
            last_heartbeat_at=observation.activity.last_heartbeat_at,
            last_heartbeat_age_seconds=age_seconds,
            last_error=observation.activity.last_error,
            last_error_at=observation.activity.last_error_at,
            status_reason=reason,
            source_mode=source_mode,
        )

    def _classify_status(
        self,
        *,
        pids: list[int],
        activity: RuntimeActivity,
        now: datetime,
    ) -> tuple[RuntimeState, str, float | None]:
        heartbeat_age_seconds: float | None = None
        if activity.last_heartbeat_at:
            heartbeat_age_seconds = max((now - activity.last_heartbeat_at).total_seconds(), 0.0)

        if not pids:
            if heartbeat_age_seconds is not None:
                return ("offline", "no matching runtime process detected", heartbeat_age_seconds)
            return ("offline", "no matching runtime process detected", None)

        if heartbeat_age_seconds is None:
            return ("degraded", "process present but no heartbeat activity found", None)

        if heartbeat_age_seconds > self._heartbeat_stale_seconds:
            return ("degraded", "process present but heartbeat is stale", heartbeat_age_seconds)

        if activity.last_error_at and activity.last_error_at >= activity.last_heartbeat_at:
            return ("degraded", "process present with recent runtime error", heartbeat_age_seconds)

        return ("running", "process present with recent heartbeat activity", heartbeat_age_seconds)
