import os
import sys
from functools import partial
from pathlib import Path

from botik_app_service.contracts.jobs import JobDetails, StartJobRequest
from botik_app_service.jobs.interfaces import JobDefinition, JobLaunchSpec

JOB_TYPE = "training_control"
FIXED_SCOPE = "futures"
FIXED_INTERVAL = "1m"


def create_training_control_job_definition(
    *,
    fixture_db_path: Path | None = None,
    manifest_path: Path | None = None,
    mode: str | None = None,
) -> JobDefinition:
    return JobDefinition(
        job_type=JOB_TYPE,
        description="Start or stop one bounded futures training flow through the existing Job Manager path.",
        launcher=partial(
            _build_launch_spec,
            fixture_db_path=fixture_db_path,
            manifest_path=manifest_path,
            configured_mode=mode,
        ),
    )


def _build_launch_spec(
    request: StartJobRequest,
    details: JobDetails,
    *,
    fixture_db_path: Path | None = None,
    manifest_path: Path | None = None,
    configured_mode: str | None = None,
) -> JobLaunchSpec:
    payload = request.payload_dict()
    scope = str(payload.get("scope", FIXED_SCOPE)).lower()
    interval = str(payload.get("interval", FIXED_INTERVAL)).lower()
    if scope != FIXED_SCOPE:
        raise ValueError(f"Unsupported training scope: {scope}")
    if interval != FIXED_INTERVAL:
        raise ValueError(f"Unsupported training interval: {interval}")

    repo_root = Path(__file__).resolve().parents[4]
    app_service_src = repo_root / "app-service" / "src"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    pythonpath_entries = [str(app_service_src), str(repo_root)]
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    control_dir = _resolve_control_dir(repo_root, env)
    control_dir.mkdir(parents=True, exist_ok=True)
    control_file = control_dir / f"{details.job_id}.stop"
    if control_file.exists():
        control_file.unlink()

    mode = _resolve_mode(env, configured_mode=configured_mode, fixture_db_path=fixture_db_path)
    command = [
        sys.executable,
        "-u",
        "-m",
        "botik_app_service.runtime.training_control_worker",
        "--job-id",
        details.job_id,
        "--scope",
        scope,
        "--interval",
        interval,
        "--mode",
        mode,
        "--control-file",
        str(control_file),
    ]

    if mode == "fixture":
        resolved_fixture_db_path = fixture_db_path or (
            Path(env["BOTIK_MODELS_READ_FIXTURE_DB_PATH"]) if env.get("BOTIK_MODELS_READ_FIXTURE_DB_PATH") else None
        )
        if resolved_fixture_db_path is None:
            raise ValueError("Fixture training control requires BOTIK_MODELS_READ_FIXTURE_DB_PATH.")
        command.extend(["--fixture-db-path", str(resolved_fixture_db_path)])
        resolved_manifest_path = manifest_path or (
            Path(env["BOTIK_MODELS_READ_MANIFEST_PATH"]) if env.get("BOTIK_MODELS_READ_MANIFEST_PATH") else None
        )
        if resolved_manifest_path is not None:
            command.extend(["--manifest-path", str(resolved_manifest_path)])

    return JobLaunchSpec(command=command, cwd=str(repo_root), env=env, control_file=control_file)


def _resolve_control_dir(repo_root: Path, env: dict[str, str]) -> Path:
    artifacts_root = env.get("BOTIK_ARTIFACTS_DIR")
    if artifacts_root:
        return Path(artifacts_root) / "state" / "training-control"
    return repo_root / ".artifacts" / "local" / "state" / "training-control"


def _resolve_mode(
    env: dict[str, str],
    *,
    configured_mode: str | None,
    fixture_db_path: Path | None,
) -> str:
    configured = (configured_mode or env.get("BOTIK_TRAINING_CONTROL_MODE", "")).strip().lower()
    if configured in {"fixture", "compatibility"}:
        return configured
    if fixture_db_path is not None or env.get("BOTIK_MODELS_READ_FIXTURE_DB_PATH"):
        return "fixture"
    return "compatibility"
