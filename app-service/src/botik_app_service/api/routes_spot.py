from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.spot import SpotReadSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.spot_read.service import SpotReadService

router = APIRouter(tags=["spot"], dependencies=[Depends(require_session_token)])


@router.get("/spot", response_model=SpotReadSnapshot)
async def get_spot_snapshot(request: Request) -> SpotReadSnapshot:
    service: SpotReadService = request.app.state.spot_read_service
    return service.snapshot()
