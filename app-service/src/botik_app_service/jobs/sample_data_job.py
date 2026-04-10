import os
import sys
from pathlib import Path

from botik_app_service.contracts.jobs import JobDetails, StartJobRequest
from botik_app_service.jobs.interfaces import JobDefinition, JobLaunchSpec

JOB_TYPE = "sample_data_import"


def create_sample_data_job_definition() -> JobDefinition:
    return JobDefinition(
        job_type=JOB_TYPE,
        description="Import deterministic sample data through the Job Manager flow.",
        launcher=_build_launch_spec,
    )


def _build_launch_spec(request: StartJobRequest, details: JobDetails) -> JobLaunchSpec:
    repo_root = Path(__file__).resolve().parents[4]
    app_service_src = repo_root / "app-service" / "src"
    fixture_path = repo_root / "app-service" / "src" / "botik_app_service" / "runtime" / "fixtures" / "sample_data.csv"
    sleep_ms = max(20, min(int(request.payload.get("sleep_ms", 80)), 1_000))

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    pythonpath_entries = [str(app_service_src), str(repo_root)]
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    command = [
        sys.executable,
        "-u",
        "-m",
        "botik_app_service.runtime.sample_data_worker",
        "--job-id",
        details.job_id,
        "--input",
        str(fixture_path),
        "--sleep-ms",
        str(sleep_ms),
    ]
    return JobLaunchSpec(command=command, cwd=str(repo_root), env=env)
