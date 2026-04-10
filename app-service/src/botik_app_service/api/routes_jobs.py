from fastapi import APIRouter, Depends, HTTPException, Request, status

from botik_app_service.contracts.jobs import JobDetails, JobSummary, StartJobRequest, StopJobRequest
from botik_app_service.infra.session import require_session_token
from botik_app_service.jobs.manager import JobManager, JobNotFoundError, UnknownJobTypeError

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_session_token)])


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(request: Request) -> list[JobSummary]:
    manager = _job_manager(request)
    return manager.list_summaries()


@router.get("/jobs/{job_id}", response_model=JobDetails)
async def get_job(job_id: str, request: Request) -> JobDetails:
    manager = _job_manager(request)
    try:
        return manager.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job: {exc.args[0]}") from exc


@router.post("/jobs", response_model=JobDetails)
async def start_job(request_model: StartJobRequest, request: Request) -> JobDetails:
    manager = _job_manager(request)
    try:
        return await manager.start(request_model)
    except UnknownJobTypeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job type: {exc.args[0]}") from exc


@router.post("/jobs/{job_id}/stop", response_model=JobDetails)
async def stop_job(job_id: str, stop_request: StopJobRequest, request: Request) -> JobDetails:
    manager = _job_manager(request)
    try:
        return await manager.stop(job_id, stop_request)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job: {exc.args[0]}") from exc
