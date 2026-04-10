import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.runtime_status.interfaces import RuntimeActivity
from botik_app_service.runtime_status.service import RuntimeStatusService


class StubProcessProbe:
    def __init__(self, processes):
        self._processes = processes

    def scan(self):
        return self._processes


class StubLegacyAdapter:
    def __init__(self, activities):
        self._activities = activities

    def read_activity(self, runtime_id):
        return self._activities[runtime_id]


class StubObservationProvider:
    def __init__(self, observations):
        self._observations = observations

    def observations(self):
        return self._observations


def test_runtime_status_service_uses_fixture_snapshot(tmp_path):
    fixture_path = tmp_path / "runtime-status.fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-11T10:00:00Z",
                "runtimes": [
                    {
                        "runtime_id": "spot",
                        "label": "Spot Runtime",
                        "state": "running",
                        "pids": [1111],
                        "pid_count": 99,
                        "last_heartbeat_at": "2026-04-11T09:59:55Z",
                        "last_heartbeat_age_seconds": 5,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "fixture running",
                        "source_mode": "compatibility",
                    },
                    {
                        "runtime_id": "futures",
                        "label": "Futures Runtime",
                        "state": "offline",
                        "pids": [],
                        "pid_count": 0,
                        "last_heartbeat_at": None,
                        "last_heartbeat_age_seconds": None,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "fixture offline",
                        "source_mode": "compatibility",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    service = RuntimeStatusService(repo_root=REPO_ROOT, heartbeat_stale_seconds=120.0, fixture_path=fixture_path)
    snapshot = service.snapshot()

    assert [runtime.runtime_id for runtime in snapshot.runtimes] == ["spot", "futures"]
    assert snapshot.runtimes[0].source_mode == "fixture"
    assert snapshot.runtimes[0].pid_count == 1


def test_runtime_status_service_classifies_running_degraded_and_offline():
    service = RuntimeStatusService(
        repo_root=REPO_ROOT,
        heartbeat_stale_seconds=120.0,
        process_probe=StubProcessProbe({"spot": [1111], "futures": []}),
        legacy_adapter=StubLegacyAdapter({"spot": RuntimeActivity(), "futures": RuntimeActivity()}),
    )
    now = service_time("2026-04-11T10:00:00Z")

    running = service._classify_status(
        pids=[1111],
        activity=RuntimeActivity(last_heartbeat_at=service_time("2026-04-11T09:59:55Z")),
        now=now,
    )
    degraded = service._classify_status(
        pids=[2222],
        activity=RuntimeActivity(last_heartbeat_at=service_time("2026-04-11T09:55:00Z")),
        now=now,
    )
    offline = service._classify_status(
        pids=[],
        activity=RuntimeActivity(last_heartbeat_at=service_time("2026-04-11T09:40:00Z")),
        now=now,
    )

    assert running[0] == "running"
    assert degraded[0] == "degraded"
    assert offline[0] == "offline"


def test_runtime_status_service_overlays_observations_over_fixture_snapshot():
    from botik_app_service.runtime_status.interfaces import RuntimeObservation

    fixture_path = REPO_ROOT / ".artifacts" / "runtime-status.test.fixture.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-11T10:00:00Z",
                "runtimes": [
                    {
                        "runtime_id": "spot",
                        "label": "Spot Runtime",
                        "state": "offline",
                        "pids": [],
                        "pid_count": 0,
                        "last_heartbeat_at": None,
                        "last_heartbeat_age_seconds": None,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "no matching runtime process detected",
                        "source_mode": "fixture",
                    },
                    {
                        "runtime_id": "futures",
                        "label": "Futures Runtime",
                        "state": "offline",
                        "pids": [],
                        "pid_count": 0,
                        "last_heartbeat_at": None,
                        "last_heartbeat_age_seconds": None,
                        "last_error": None,
                        "last_error_at": None,
                        "status_reason": "no matching runtime process detected",
                        "source_mode": "fixture",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        service = RuntimeStatusService(
            repo_root=REPO_ROOT,
            heartbeat_stale_seconds=120.0,
            fixture_path=fixture_path,
            observation_provider=StubObservationProvider(
                {
                    "spot": RuntimeObservation(
                        runtime_id="spot",
                        label="Spot Runtime",
                        pids=[9999],
                        activity=RuntimeActivity(last_heartbeat_at=service_time("2026-04-11T09:59:59Z")),
                    )
                }
            ),
        )

        snapshot = service.snapshot()
        spot = snapshot.runtimes[0]
        futures = snapshot.runtimes[1]
        assert spot.state == "running"
        assert spot.pid_count == 1
        assert futures.state == "offline"
    finally:
        fixture_path.unlink(missing_ok=True)


def service_time(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))
