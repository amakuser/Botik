from fastapi import APIRouter, Depends, Query, Request

from botik_app_service.contracts.orderbook import OrderbookSnapshot
from botik_app_service.infra.session import require_session_token
from botik_app_service.orderbook_read.service import OrderbookReadService

router = APIRouter(tags=["orderbook"], dependencies=[Depends(require_session_token)])


@router.get("/orderbook", response_model=OrderbookSnapshot)
async def get_orderbook(
    request: Request,
    symbol: str = Query(default="BTCUSDT"),
    category: str = Query(default="linear"),
) -> OrderbookSnapshot:
    service: OrderbookReadService = request.app.state.orderbook_read_service
    return service.snapshot(symbol=symbol, category=category)
