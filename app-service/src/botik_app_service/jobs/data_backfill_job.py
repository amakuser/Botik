import os
import sys
from pathlib import Path

from botik_app_service.contracts.jobs import JobDetails, StartJobRequest
from botik_app_service.jobs.interfaces import JobDefinition, JobLaunchSpec

JOB_TYPE = "data_backfill"
FIXED_SYMBOL = "BTCUSDT"
FIXED_CATEGORY = "spot"
FIXED_INTERVALS = ["1m"]


def create_data_backfill_job_definition() -> JobDefinition:
    return JobDefinition(
        job_type=JOB_TYPE,
        description="Run one fixed-preset data backfill through the Job Manager flow.",
        launcher=_build_launch_spec,
    )


def _build_launch_spec(request: StartJobRequest, details: JobDetails) -> JobLaunchSpec:
    payload = request.payload_dict()
    symbol = str(payload.get("symbol", FIXED_SYMBOL)).upper()
    category = str(payload.get("category", FIXED_CATEGORY)).lower()
    intervals = [str(interval) for interval in payload.get("intervals", FIXED_INTERVALS)]
    if symbol != FIXED_SYMBOL:
        raise ValueError(f"Unsupported backfill symbol: {symbol}")
    if category != FIXED_CATEGORY:
        raise ValueError(f"Unsupported backfill category: {category}")
    if intervals != FIXED_INTERVALS:
        raise ValueError(f"Unsupported backfill intervals: {intervals}")

    repo_root = Path(__file__).resolve().parents[4]
    app_service_src = repo_root / "app-service" / "src"
    fixture_path = repo_root / "app-service" / "src" / "botik_app_service" / "runtime" / "fixtures" / "data_backfill_klines.json"

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    pythonpath_entries = [str(app_service_src), str(repo_root)]
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    db_url = _resolve_slice_db_url(repo_root, env)
    env["DB_URL"] = db_url

    command = [
        sys.executable,
        "-u",
        "-m",
        "botik_app_service.runtime.data_backfill_worker",
        "--job-id",
        details.job_id,
        "--symbol",
        symbol,
        "--category",
        category,
        "--intervals",
        *intervals,
        "--db-url",
        db_url,
        "--source",
        "fixture",
        "--fixture",
        str(fixture_path),
    ]
    return JobLaunchSpec(command=command, cwd=str(repo_root), env=env)


def _resolve_slice_db_url(repo_root: Path, env: dict[str, str]) -> str:
    artifacts_root = env.get("BOTIK_ARTIFACTS_DIR")
    if artifacts_root:
        state_dir = Path(artifacts_root) / "state"
    else:
        state_dir = repo_root / ".artifacts" / "local" / "state" / "data-backfill"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = (state_dir / "data_backfill.sqlite3").resolve()
    return f"sqlite:///{db_path.as_posix()}"
