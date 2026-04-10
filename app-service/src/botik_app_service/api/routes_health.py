from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.health import HealthResponse
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, dependencies=[Depends(require_session_token)])
async def get_health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        session_id=settings.session_token,
    )
