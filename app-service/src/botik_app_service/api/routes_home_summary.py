from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.home_summary import HomeSummary
from botik_app_service.home.service import HomeSummaryService
from botik_app_service.infra.session import require_session_token

router = APIRouter(tags=["home"], dependencies=[Depends(require_session_token)])


@router.get("/home/summary", response_model=HomeSummary, response_model_by_alias=True)
async def get_home_summary(request: Request) -> HomeSummary:
    service: HomeSummaryService = request.app.state.home_summary_service
    return service.get_summary()
