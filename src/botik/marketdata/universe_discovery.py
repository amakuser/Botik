"""
Public market discovery helpers for dynamic spot/linear symbol universe.
"""
from __future__ import annotations

from typing import Any

import aiohttp

from src.botik.marketdata.symbol_universe import fetch_spot_instruments, filter_spot_symbols


def _pick_ranked_symbols(
    candidates: list[tuple[float, float, float, str]],
    *,
    limit: int,
    min_symbols: int,
    min_turnover_24h: float,
    min_raw_spread_bps: float,
    min_top_book_notional: float,
) -> list[str]:
    def _pick(
        turnover_floor: float,
        spread_floor: float,
        notional_floor: float,
        size: int,
    ) -> list[str]:
        ranked: list[tuple[float, float, float, str]] = []
        for raw_spread_bps, top_book_notional, turnover, symbol in candidates:
            if turnover < turnover_floor:
                continue
            if raw_spread_bps < spread_floor:
                continue
            if top_book_notional < notional_floor:
                continue
            ranked.append((raw_spread_bps, top_book_notional, turnover, symbol))
        ranked.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return [symbol for _, _, _, symbol in ranked[:size]]

    size = max(int(limit), 1)
    min_size = max(int(min_symbols), 0)
    target_size = max(size, min_size)

    turnover_floor = max(float(min_turnover_24h), 0.0)
    spread_floor = max(float(min_raw_spread_bps), 0.0)
    notional_floor = max(float(min_top_book_notional), 0.0)
    picked = _pick(turnover_floor, spread_floor, notional_floor, target_size)
    if len(picked) >= target_size:
        return picked

    for _ in range(6):
        turnover_floor *= 0.5
        spread_floor *= 0.5
        notional_floor *= 0.5
        picked = _pick(turnover_floor, spread_floor, notional_floor, target_size)
        if len(picked) >= target_size:
            break
        if turnover_floor <= 1.0 and spread_floor <= 0.01 and notional_floor <= 1.0:
            break
    return picked


async def discover_top_spot_symbols(
    host: str = "api.bybit.com",
    quote: str = "USDT",
    limit: int = 20,
    min_symbols: int = 0,
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
    candidates: list[tuple[float, float, float, str]] = []
    for item in items:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol or symbol not in allowed_symbols:
            continue

        turnover = float(item.get("turnover24h") or 0.0)
        bid = float(item.get("bid1Price") or 0.0)
        ask = float(item.get("ask1Price") or 0.0)
        bid_size = float(item.get("bid1Size") or 0.0)
        ask_size = float(item.get("ask1Size") or 0.0)
        if bid <= 0 or ask <= 0 or ask <= bid or bid_size <= 0 or ask_size <= 0:
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            continue
        raw_spread_bps = ((ask - bid) / mid) * 10000.0
        top_book_notional = min(bid * bid_size, ask * ask_size)
        candidates.append((raw_spread_bps, top_book_notional, turnover, symbol))

    return _pick_ranked_symbols(
        candidates,
        limit=limit,
        min_symbols=min_symbols,
        min_turnover_24h=min_turnover_24h,
        min_raw_spread_bps=min_raw_spread_bps,
        min_top_book_notional=min_top_book_notional,
    )


async def discover_top_linear_symbols(
    host: str = "api.bybit.com",
    quote: str = "USDT",
    limit: int = 20,
    min_symbols: int = 0,
    min_turnover_24h: float = 0.0,
    min_raw_spread_bps: float = 0.0,
    min_top_book_notional: float = 0.0,
) -> list[str]:
    """
    Discover top linear perpetual symbols from Bybit public REST.
    Ranking prefers high raw spread, then top-of-book notional, then turnover24h.
    """
    quote_u = quote.upper().strip()
    url = f"https://{host}/v5/market/tickers"
    params = {"category": "linear"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=20) as resp:
            out: dict[str, Any] = await resp.json()

    if out.get("retCode") != 0:
        raise RuntimeError(f"discover_top_linear_symbols failed: retCode={out.get('retCode')} retMsg={out.get('retMsg')}")

    items = (out.get("result") or {}).get("list") or []
    candidates: list[tuple[float, float, float, str]] = []
    for item in items:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        if quote_u and not symbol.endswith(quote_u):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status and status not in {"trading", "tradable"}:
            continue

        turnover = float(item.get("turnover24h") or 0.0)
        bid = float(item.get("bid1Price") or 0.0)
        ask = float(item.get("ask1Price") or 0.0)
        bid_size = float(item.get("bid1Size") or 0.0)
        ask_size = float(item.get("ask1Size") or 0.0)
        if bid <= 0 or ask <= 0 or ask <= bid or bid_size <= 0 or ask_size <= 0:
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            continue
        raw_spread_bps = ((ask - bid) / mid) * 10000.0
        top_book_notional = min(bid * bid_size, ask * ask_size)
        candidates.append((raw_spread_bps, top_book_notional, turnover, symbol))

    return _pick_ranked_symbols(
        candidates,
        limit=limit,
        min_symbols=min_symbols,
        min_turnover_24h=min_turnover_24h,
        min_raw_spread_bps=min_raw_spread_bps,
        min_top_book_notional=min_top_book_notional,
    )


async def discover_top_symbols_by_category(
    category: str,
    *,
    host: str = "api.bybit.com",
    quote: str = "USDT",
    limit: int = 20,
    min_symbols: int = 0,
    min_turnover_24h: float = 0.0,
    min_raw_spread_bps: float = 0.0,
    min_top_book_notional: float = 0.0,
    exclude_st_tag_1: bool = True,
) -> list[str]:
    cat = str(category or "").strip().lower()
    if cat == "linear":
        return await discover_top_linear_symbols(
            host=host,
            quote=quote,
            limit=limit,
            min_symbols=min_symbols,
            min_turnover_24h=min_turnover_24h,
            min_raw_spread_bps=min_raw_spread_bps,
            min_top_book_notional=min_top_book_notional,
        )
    return await discover_top_spot_symbols(
        host=host,
        quote=quote,
        limit=limit,
        min_symbols=min_symbols,
        min_turnover_24h=min_turnover_24h,
        min_raw_spread_bps=min_raw_spread_bps,
        min_top_book_notional=min_top_book_notional,
        exclude_st_tag_1=exclude_st_tag_1,
    )
