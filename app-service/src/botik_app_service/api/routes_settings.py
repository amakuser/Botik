from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.settings import (
    BybitTestRequest,
    BybitTestResult,
    SettingsSaveRequest,
    SettingsSaveResult,
    SettingsSnapshot,
)
from botik_app_service.infra.session import require_session_token
from botik_app_service.settings_read.service import SettingsReadService

router = APIRouter(tags=["settings"], dependencies=[Depends(require_session_token)])


@router.get("/settings", response_model=SettingsSnapshot)
async def get_settings_snapshot(request: Request) -> SettingsSnapshot:
    service: SettingsReadService = request.app.state.settings_read_service
    return service.snapshot()


@router.post("/settings", response_model=SettingsSaveResult)
async def save_settings(request: Request, body: SettingsSaveRequest) -> SettingsSaveResult:
    service: SettingsReadService = request.app.state.settings_read_service
    return service.save(body)


@router.post("/settings/test-bybit", response_model=BybitTestResult)
async def test_bybit_api(request: Request, body: BybitTestRequest) -> BybitTestResult:
    service: SettingsReadService = request.app.state.settings_read_service
    return service.test_bybit(body)
