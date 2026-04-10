from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.runtime_status import RuntimeStatusSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.runtime_status.service import RuntimeStatusService

router = APIRouter(tags=["runtime-status"], dependencies=[Depends(require_session_token)])


@router.get("/runtime-status", response_model=RuntimeStatusSnapshot)
async def get_runtime_status(request: Request) -> RuntimeStatusSnapshot:
    service: RuntimeStatusService = request.app.state.runtime_status_service
    return service.snapshot()
