from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.runtime_status import RuntimeId, RuntimeStatus
from botik_app_service.infra.session import require_session_token
from botik_app_service.runtime_control.service import RuntimeControlService
from botik_app_service.runtime_status.service import RuntimeStatusService

router = APIRouter(tags=["runtime-control"], dependencies=[Depends(require_session_token)])


def _get_runtime_snapshot(request: Request, runtime_id: RuntimeId) -> RuntimeStatus:
    status_service: RuntimeStatusService = request.app.state.runtime_status_service
    return status_service.runtime_status(runtime_id)


@router.post("/runtime-control/{runtime_id}/start", response_model=RuntimeStatus)
async def start_runtime(runtime_id: RuntimeId, request: Request) -> RuntimeStatus:
    service: RuntimeControlService = request.app.state.runtime_control_service
    await service.start(runtime_id)
    return _get_runtime_snapshot(request, runtime_id)


@router.post("/runtime-control/{runtime_id}/stop", response_model=RuntimeStatus)
async def stop_runtime(runtime_id: RuntimeId, request: Request) -> RuntimeStatus:
    service: RuntimeControlService = request.app.state.runtime_control_service
    await service.stop(runtime_id)
    return _get_runtime_snapshot(request, runtime_id)
