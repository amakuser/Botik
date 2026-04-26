from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.reconciliation import ReconciliationSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.reconciliation_read.manager import ReconciliationReadService

router = APIRouter(tags=["reconciliation"], dependencies=[Depends(require_session_token)])


@router.get("/reconciliation", response_model=ReconciliationSnapshot)
async def get_reconciliation(request: Request) -> ReconciliationSnapshot:
    service: ReconciliationReadService = request.app.state.reconciliation_read_service
    return service.snapshot()
