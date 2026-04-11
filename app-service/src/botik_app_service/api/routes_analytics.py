from fastapi import APIRouter, Depends, Request

from botik_app_service.analytics_read.service import AnalyticsReadService
from botik_app_service.contracts.analytics import AnalyticsReadSnapshot
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["analytics"], dependencies=[Depends(require_session_token)])


@router.get("/analytics", response_model=AnalyticsReadSnapshot)
async def get_analytics_snapshot(request: Request) -> AnalyticsReadSnapshot:
    service: AnalyticsReadService = request.app.state.analytics_read_service
    return service.snapshot()
