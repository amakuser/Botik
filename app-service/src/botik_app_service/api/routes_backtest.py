import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Request

from botik_app_service.contracts.backtest import BacktestRunRequest, BacktestRunResult
from botik_app_service.infra.session import require_session_token
from botik_app_service.backtest_run.service import BacktestRunService

router = APIRouter(tags=["backtest"], dependencies=[Depends(require_session_token)])

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")


@router.post("/backtest/run", response_model=BacktestRunResult)
async def run_backtest(request: Request, body: BacktestRunRequest) -> BacktestRunResult:
    service: BacktestRunService = request.app.state.backtest_run_service
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, service.run, body)
