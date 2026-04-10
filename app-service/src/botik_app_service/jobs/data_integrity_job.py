import os
import sys
from pathlib import Path

from botik_app_service.contracts.jobs import JobDetails, StartJobRequest
from botik_app_service.jobs.data_backfill_job import resolve_data_backfill_db_url
from botik_app_service.jobs.interfaces import JobDefinition, JobLaunchSpec

JOB_TYPE = "data_integrity"
FIXED_SYMBOL = "BTCUSDT"
FIXED_CATEGORY = "spot"
FIXED_INTERVALS = ["1m"]


def create_data_integrity_job_definition() -> JobDefinition:
    return JobDefinition(
        job_type=JOB_TYPE,
        description="Validate the fixed-preset data backfill DB without touching the legacy runtime DB.",
        launcher=_build_launch_spec,
    )


def _build_launch_spec(request: StartJobRequest, details: JobDetails) -> JobLaunchSpec:
    payload = request.payload_dict()
    symbol = str(payload.get("symbol", FIXED_SYMBOL)).upper()
    category = str(payload.get("category", FIXED_CATEGORY)).lower()
    intervals = [str(interval) for interval in payload.get("intervals", FIXED_INTERVALS)]
    if symbol != FIXED_SYMBOL:
        raise ValueError(f"Unsupported integrity symbol: {symbol}")
    if category != FIXED_CATEGORY:
        raise ValueError(f"Unsupported integrity category: {category}")
    if intervals != FIXED_INTERVALS:
        raise ValueError(f"Unsupported integrity intervals: {intervals}")

    repo_root = Path(__file__).resolve().parents[4]
    app_service_src = repo_root / "app-service" / "src"

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    pythonpath_entries = [str(app_service_src), str(repo_root)]
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    db_url = resolve_data_backfill_db_url(repo_root, env)
    env["DB_URL"] = db_url

    command = [
        sys.executable,
        "-u",
        "-m",
        "botik_app_service.runtime.data_integrity_worker",
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
    ]
    return JobLaunchSpec(command=command, cwd=str(repo_root), env=env)
