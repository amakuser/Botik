from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.db_health import DbHealthSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.db_health.service import DbHealthService

router = APIRouter(tags=["db-health"], dependencies=[Depends(require_session_token)])


@router.get("/db-health", response_model=DbHealthSnapshot)
async def get_db_health(request: Request) -> DbHealthSnapshot:
    # Real probe on every call — no caching.
    # Rationale: latency check is the point; stale cache would defeat the signal.
    # SELECT 1 on SQLite is microseconds; the 2s connect timeout is the worst case.
    service: DbHealthService = request.app.state.db_health_service
    return service.snapshot()
