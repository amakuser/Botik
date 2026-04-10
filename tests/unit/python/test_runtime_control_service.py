import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.jobs.process_adapter import ProcessAdapter
from botik_app_service.runtime_control.service import RuntimeControlService


def test_runtime_control_service_manages_fixture_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", f"{REPO_ROOT / 'app-service' / 'src'};{REPO_ROOT}")

    async def scenario():
        service = RuntimeControlService(
            repo_root=REPO_ROOT,
            process_adapter=ProcessAdapter(),
            mode="fixture",
            artifacts_dir=tmp_path,
            heartbeat_interval_seconds=0.1,
            stop_timeout_seconds=4.0,
        )
        try:
            await service.start("spot")
            deadline = asyncio.get_running_loop().time() + 3.0
            while asyncio.get_running_loop().time() < deadline:
                observations = service.observations()
                if observations.get("spot") and observations["spot"].activity.last_heartbeat_at is not None:
                    break
                await asyncio.sleep(0.05)
            observations = service.observations()
            assert "spot" in observations
            assert observations["spot"].pids

            await service.stop("spot")
            await asyncio.sleep(0.1)
            assert "spot" not in service.observations()
        finally:
            await service.shutdown()

    asyncio.run(scenario())
