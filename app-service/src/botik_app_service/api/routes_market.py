from fastapi import APIRouter, Depends, Query, Request

from botik_app_service.contracts.market import MarketTickerSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.market_read.service import MarketReadService

router = APIRouter(tags=["market"], dependencies=[Depends(require_session_token)])


@router.get("/market-ticker", response_model=MarketTickerSnapshot)
async def get_market_ticker(
    request: Request,
    symbols: str = Query(default="", description="Comma-separated symbols, empty = default set"),
) -> MarketTickerSnapshot:
    service: MarketReadService = request.app.state.market_read_service
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return service.snapshot(symbol_list)
