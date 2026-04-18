from pathlib import Path
from decimal import Decimal

import httpx

from botik_app_service.contracts.orderbook import OrderbookLevel, OrderbookSnapshot

_BYBIT_URL = "https://api.bybit.com/v5/market/orderbook"
_DEPTH = 25


class OrderbookReadService:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def snapshot(self, symbol: str, category: str) -> OrderbookSnapshot:
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(
                    _BYBIT_URL,
                    params={"category": category, "symbol": symbol, "limit": _DEPTH},
                )
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode", -1) != 0:
                return OrderbookSnapshot(
                    symbol=symbol,
                    category=category,  # type: ignore[arg-type]
                    error=data.get("retMsg", "API error"),
                )
            result = data.get("result", {})
            bids = _parse_levels(result.get("b", []), descending=True)
            asks = _parse_levels(result.get("a", []), descending=False)
            return OrderbookSnapshot(symbol=symbol, category=category, bids=bids, asks=asks)  # type: ignore[arg-type]
        except Exception as exc:
            return OrderbookSnapshot(symbol=symbol, category=category, error=str(exc))  # type: ignore[arg-type]


def _parse_levels(raw: list[list[str]], *, descending: bool) -> list[OrderbookLevel]:
    levels: list[OrderbookLevel] = []
    cumulative = Decimal("0")
    for entry in raw:
        if len(entry) < 2:
            continue
        price_str, size_str = entry[0], entry[1]
        try:
            size = Decimal(size_str)
            price = Decimal(price_str)
            cumulative += size * price
            levels.append(
                OrderbookLevel(
                    price=price_str,
                    size=size_str,
                    total=str(cumulative.quantize(Decimal("0.01"))),
                )
            )
        except Exception:
            continue
    if descending:
        levels.sort(key=lambda l: Decimal(l.price), reverse=True)
    else:
        levels.sort(key=lambda l: Decimal(l.price))
    return levels
