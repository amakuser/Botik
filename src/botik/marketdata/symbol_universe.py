"""
Bybit Spot symbol universe from instruments-info.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class SpotInstrument:
    symbol: str
    quote_coin: str
    status: str
    st_tag: str


async def fetch_spot_instruments(host: str = "api.bybit.com") -> list[SpotInstrument]:
    """
    Load spot instruments from V5 instruments-info.
    For spot, pagination is not required by Bybit docs.
    """
    url = f"https://{host}/v5/market/instruments-info"
    params = {"category": "spot"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=20) as resp:
            out: dict[str, Any] = await resp.json()

    if out.get("retCode") != 0:
        raise RuntimeError(f"fetch_spot_instruments failed: retCode={out.get('retCode')} retMsg={out.get('retMsg')}")

    result_list = (out.get("result") or {}).get("list") or []
    instruments: list[SpotInstrument] = []
    for item in result_list:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        instruments.append(
            SpotInstrument(
                symbol=symbol,
                quote_coin=str(item.get("quoteCoin") or "").upper().strip(),
                status=str(item.get("status") or "").strip(),
                st_tag=str(item.get("stTag") or "").strip(),
            )
        )
    return instruments


def filter_spot_symbols(
    instruments: list[SpotInstrument],
    quote_coin: str = "USDT",
    exclude_st_tag_1: bool = True,
) -> list[str]:
    """
    Keep only spot pairs allowed for trading scanner.
    """
    q = quote_coin.upper().strip()
    out: list[str] = []
    for item in instruments:
        if q and item.quote_coin != q:
            continue
        if item.status != "Trading":
            continue
        if exclude_st_tag_1 and item.st_tag == "1":
            continue
        out.append(item.symbol)
    return out
