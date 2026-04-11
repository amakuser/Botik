from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.futures import FuturesReadSnapshot
from botik_app_service.futures_read.service import FuturesReadService
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["futures"], dependencies=[Depends(require_session_token)])


@router.get("/futures", response_model=FuturesReadSnapshot)
async def get_futures_snapshot(request: Request) -> FuturesReadSnapshot:
    service: FuturesReadService = request.app.state.futures_read_service
    return service.snapshot()
