"""
Preflight checks for production startup/update.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import aiohttp
import websockets

from src.botik.config import load_config
from src.botik.execution.bybit_rest import BybitRestClient


def _sanitize_category(category: str) -> str:
    value = str(category or "").strip().lower()
    if value in {"spot", "linear"}:
        return value
    return "spot"


async def _check_ws(ws_host: str, symbol: str, depth: int, timeout_sec: float, category: str) -> dict[str, Any]:
    cat = _sanitize_category(category)
    url = f"wss://{ws_host}/v5/public/{cat}"
    topic = f"orderbook.{depth}.{symbol}"
    async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
        msg = json.loads(raw)
        if msg.get("topic") != topic:
            # First packet can be subscription status; fetch one more.
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
            msg = json.loads(raw)
        if msg.get("topic") != topic:
            raise RuntimeError(f"WS unexpected topic: {msg}")
        data = msg.get("data") or {}
        bids = data.get("b") or []
        asks = data.get("a") or []
        if not bids or not asks:
            raise RuntimeError("WS has no top-of-book data")
        bid = float(bids[0][0])
        ask = float(asks[0][0])
        if bid <= 0 or ask <= 0 or ask <= bid:
            raise RuntimeError(f"Invalid top-of-book bid={bid} ask={ask}")
        return {"ok": True, "host": ws_host, "symbol": symbol, "category": cat, "bid": bid, "ask": ask}


async def _check_rest_public(rest_host: str) -> dict[str, Any]:
    url = f"https://{rest_host}/v5/market/time"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as resp:
            out = await resp.json()
    if out.get("retCode") != 0:
        raise RuntimeError(f"REST public time failed: {out}")
    return {"ok": True, "host": rest_host, "retCode": out.get("retCode")}


async def _check_rest_auth(config_path: str | None, symbol: str) -> dict[str, Any]:
    cfg = load_config(config_path)
    category = _sanitize_category(cfg.bybit.market_category)
    api_key = cfg.get_bybit_api_key()
    api_secret = cfg.get_bybit_api_secret()
    rsa_private_key_path = cfg.get_bybit_rsa_private_key_path()
    if not api_key or (not api_secret and not rsa_private_key_path):
        raise RuntimeError("Missing BYBIT credentials for authenticated preflight check.")
    client = BybitRestClient(
        base_url=f"https://{cfg.bybit.host}",
        api_key=api_key,
        api_secret=api_secret,
        rsa_private_key_path=rsa_private_key_path,
        category=category,
    )
    out = await client.get_open_orders(symbol=symbol)
    if out.get("retCode") != 0:
        raise RuntimeError(
            f"REST auth check failed: retCode={out.get('retCode')} retMsg={out.get('retMsg')}"
        )
    return {"ok": True, "retCode": out.get("retCode"), "auth_mode": client.auth_mode, "category": category}


async def _run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    category = _sanitize_category(cfg.bybit.market_category)
    symbol = args.symbol or (cfg.symbols[0] if cfg.symbols else "BTCUSDT")
    result: dict[str, Any] = {
        "mode": cfg.execution.mode,
        "category": category,
        "symbol": symbol,
        "checks": {},
    }
    try:
        result["checks"]["ws"] = await _check_ws(
            ws_host=cfg.bybit.ws_public_host,
            symbol=symbol,
            depth=cfg.ws_depth,
            timeout_sec=args.timeout_sec,
            category=category,
        )
        result["checks"]["rest_public"] = await _check_rest_public(cfg.bybit.host)
        if not args.skip_auth and cfg.execution.mode.lower().strip() == "live":
            result["checks"]["rest_auth"] = await _check_rest_auth(args.config, symbol)
        else:
            result["checks"]["rest_auth"] = {"ok": True, "skipped": True}
        print(f"PREFLIGHT_OK {json.dumps(result, ensure_ascii=False, sort_keys=True)}")
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        print(f"PREFLIGHT_FAIL {json.dumps(result, ensure_ascii=False, sort_keys=True)}")
        return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Botik production preflight checks")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--symbol", default="", help="Symbol for checks, default first from config")
    parser.add_argument("--timeout-sec", type=float, default=15.0, help="Timeout for WS and REST checks")
    parser.add_argument("--skip-auth", action="store_true", help="Skip authenticated REST check")
    args = parser.parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
