from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.models import ModelsReadSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.models_read.service import ModelsReadService

router = APIRouter(tags=["models"], dependencies=[Depends(require_session_token)])


@router.get("/models", response_model=ModelsReadSnapshot)
async def get_models_snapshot(request: Request) -> ModelsReadSnapshot:
    service: ModelsReadService = request.app.state.models_read_service
    return service.snapshot()
