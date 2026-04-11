from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.diagnostics import DiagnosticsSnapshot
from botik_app_service.diagnostics_compat.service import DiagnosticsCompatibilityService
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["diagnostics"], dependencies=[Depends(require_session_token)])


@router.get("/diagnostics", response_model=DiagnosticsSnapshot)
async def get_diagnostics_snapshot(request: Request) -> DiagnosticsSnapshot:
    service: DiagnosticsCompatibilityService = request.app.state.diagnostics_service
    return service.snapshot()
