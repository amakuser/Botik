import time
from pathlib import Path

import httpx

from botik_app_service.contracts.market import MarketTickerEntry, MarketTickerSnapshot

_DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "DOGEUSDT",
    "LTCUSDT", "MATICUSDT",
]

_BYBIT_PUBLIC_URL = "https://api.bybit.com/v5/market/tickers"


class MarketReadService:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def snapshot(self, symbols: list[str] | None = None) -> MarketTickerSnapshot:
        target_symbols = set(symbols or _DEFAULT_SYMBOLS)
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(_BYBIT_PUBLIC_URL, params={"category": "linear"})
            resp.raise_for_status()
            data = resp.json()
            raw_list: list[dict] = data.get("result", {}).get("list", [])
            tickers = [
                MarketTickerEntry(
                    symbol=item["symbol"],
                    last_price=item.get("lastPrice", "0"),
                    price_24h_pcnt=item.get("price24hPcnt", "0"),
                    turnover_24h=item.get("turnover24h", "0"),
                    high_price_24h=item.get("highPrice24h", "0"),
                    low_price_24h=item.get("lowPrice24h", "0"),
                )
                for item in raw_list
                if item.get("symbol") in target_symbols
            ]
            # Sort by target_symbols order
            order = {s: i for i, s in enumerate(_DEFAULT_SYMBOLS)}
            tickers.sort(key=lambda t: order.get(t.symbol, 999))
            return MarketTickerSnapshot(tickers=tickers)
        except Exception as exc:
            return MarketTickerSnapshot(tickers=[], error=str(exc))
