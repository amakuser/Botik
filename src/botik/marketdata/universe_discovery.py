"""
Public market discovery helpers for dynamic spot symbol universe.
"""
from __future__ import annotations

from typing import Any

import aiohttp

from src.botik.marketdata.symbol_universe import fetch_spot_instruments, filter_spot_symbols


async def discover_top_spot_symbols(
    host: str = "api.bybit.com",
    quote: str = "USDT",
    limit: int = 20,
    min_turnover_24h: float = 0.0,
    min_raw_spread_bps: float = 0.0,
    min_top_book_notional: float = 0.0,
    exclude_st_tag_1: bool = True,
) -> list[str]:
    """
    Discover top spot symbols from Bybit public REST.
    Universe source is instruments-info (spot), filtered by quote/status/stTag.
    Ranking prefers high raw spread, then top-of-book notional, then turnover24h.
    """
    quote_u = quote.upper().strip()
    instruments = await fetch_spot_instruments(host=host)
    allowed_symbols = set(filter_spot_symbols(instruments, quote_coin=quote_u, exclude_st_tag_1=exclude_st_tag_1))
    if not allowed_symbols:
        return []

    url = f"https://{host}/v5/market/tickers"
    params = {"category": "spot"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=20) as resp:
            out: dict[str, Any] = await resp.json()

    if out.get("retCode") != 0:
        raise RuntimeError(f"discover_top_spot_symbols failed: retCode={out.get('retCode')} retMsg={out.get('retMsg')}")

    items = (out.get("result") or {}).get("list") or []
    ranked: list[tuple[float, float, float, str]] = []
    for item in items:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in allowed_symbols:
            continue

        turnover = float(item.get("turnover24h") or 0.0)
        if turnover < max(min_turnover_24h, 0.0):
            continue

        bid = float(item.get("bid1Price") or 0.0)
        ask = float(item.get("ask1Price") or 0.0)
        if bid <= 0 or ask <= 0 or ask <= bid:
            continue
        bid_size = float(item.get("bid1Size") or 0.0)
        ask_size = float(item.get("ask1Size") or 0.0)
        if bid_size <= 0 or ask_size <= 0:
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            continue
        raw_spread_bps = ((ask - bid) / mid) * 10000.0
        top_book_notional = min(bid * bid_size, ask * ask_size)

        if raw_spread_bps < max(min_raw_spread_bps, 0.0):
            continue
        if top_book_notional < max(min_top_book_notional, 0.0):
            continue

        ranked.append((raw_spread_bps, top_book_notional, turnover, symbol))

    ranked.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    size = max(int(limit), 1)
    return [symbol for _, _, _, symbol in ranked[:size]]
