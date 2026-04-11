from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.telegram import TelegramConnectivityCheckResult, TelegramOpsSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.telegram_ops.service import TelegramOpsService

router = APIRouter(tags=["telegram"], dependencies=[Depends(require_session_token)])


@router.get("/telegram", response_model=TelegramOpsSnapshot)
async def get_telegram_snapshot(request: Request) -> TelegramOpsSnapshot:
    service: TelegramOpsService = request.app.state.telegram_ops_service
    return service.snapshot()


@router.post("/telegram/connectivity-check", response_model=TelegramConnectivityCheckResult)
async def run_telegram_connectivity_check(request: Request) -> TelegramConnectivityCheckResult:
    service: TelegramOpsService = request.app.state.telegram_ops_service
    return service.run_connectivity_check()
