"""
Bybit WS/REST smoke test for reliability checks.

Examples:
  python bybit_smoke_test.py --symbol BTCUSDT
  python bybit_smoke_test.py --symbol BTCUSDT --compare-host stream-testnet.bybit.com
  python bybit_smoke_test.py --symbol BTCUSDT --check-rest-order --auth-mode hmac --keep-order-open
  python bybit_smoke_test.py --symbol BTCUSDT --check-rest-order --auth-mode hmac --cancel-created-order
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any

import aiohttp
import websockets
from dotenv import load_dotenv

from src.botik.execution.bybit_rest import BybitRestClient


def _fmt_decimal(value: Decimal) -> str:
    s = format(value, "f").rstrip("0").rstrip(".")
    return s or "0"


def _quantize_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _quantize_up(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_UP) * step


async def _read_ws_top_of_book(
    ws_host: str,
    symbol: str,
    depth: int,
    samples: int,
    timeout_sec: float,
) -> list[tuple[Decimal, Decimal]]:
    url = f"wss://{ws_host}/v5/public/spot"
    topic = f"orderbook.{depth}.{symbol}"
    out: list[tuple[Decimal, Decimal]] = []
    async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
        while len(out) < samples:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
            msg = json.loads(raw)
            if msg.get("topic") != topic:
                continue
            data = msg.get("data") or {}
            bids = data.get("b") or []
            asks = data.get("a") or []
            if not bids or not asks:
                continue
            bid = Decimal(str(bids[0][0]))
            ask = Decimal(str(asks[0][0]))
            out.append((bid, ask))
    return out


def _summarize(samples: list[tuple[Decimal, Decimal]]) -> dict[str, Decimal]:
    mids = [(b + a) / Decimal("2") for b, a in samples]
    spreads = [a - b for b, a in samples]
    return {
        "bid": samples[-1][0],
        "ask": samples[-1][1],
        "mid_avg": sum(mids) / Decimal(len(mids)),
        "spread_avg": sum(spreads) / Decimal(len(spreads)),
    }


async def _public_get(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=20) as resp:
            return await resp.json()


def _resolve_auth(auth_mode: str) -> tuple[str, str | None, str | None, str]:
    api_key = os.getenv("BYBIT_API_KEY", "").strip()
    hmac_secret = (os.getenv("BYBIT_API_SECRET_KEY", "") or os.getenv("BYBIT_API_SECRET", "")).strip()
    rsa_key_path = os.getenv("BYBIT_RSA_PRIVATE_KEY_PATH", "").strip() or None
    if not api_key:
        raise RuntimeError("BYBIT_API_KEY is not set.")

    if auth_mode == "hmac":
        if not hmac_secret:
            raise RuntimeError("auth-mode=hmac requires BYBIT_API_SECRET_KEY (or BYBIT_API_SECRET).")
        return api_key, hmac_secret, None, "hmac"
    if auth_mode == "rsa":
        if not rsa_key_path:
            raise RuntimeError("auth-mode=rsa requires BYBIT_RSA_PRIVATE_KEY_PATH.")
        return api_key, None, rsa_key_path, "rsa"

    # auto
    if hmac_secret:
        return api_key, hmac_secret, None, "hmac"
    if rsa_key_path:
        return api_key, None, rsa_key_path, "rsa"
    raise RuntimeError("Set BYBIT_API_SECRET_KEY (preferred) or BYBIT_RSA_PRIVATE_KEY_PATH.")


async def _rest_order_lifecycle(
    rest_host: str,
    symbol: str,
    side: str,
    price_offset_pct: Decimal,
    auth_mode: str,
    keep_order_open: bool,
    cancel_created_order: bool,
) -> tuple[bool, dict[str, Any]]:
    api_key, api_secret, rsa_key_path, selected_auth_mode = _resolve_auth(auth_mode)
    base_url = f"https://{rest_host}"
    result_payload: dict[str, Any] = {
        "auth_mode": selected_auth_mode,
        "symbol": symbol,
        "rest_host": rest_host,
        "created": False,
        "found_in_open_orders": False,
        "cancelled": False,
    }

    inst = await _public_get(
        base_url,
        "/v5/market/instruments-info",
        {"category": "spot", "symbol": symbol},
    )
    if inst.get("retCode") != 0:
        return False, {"error": f"instruments-info failed: {inst}"}
    inst_list = ((inst.get("result") or {}).get("list") or [])
    if not inst_list:
        return False, {"error": f"instrument not found: {symbol}"}
    instrument = inst_list[0]

    ticker = await _public_get(
        base_url,
        "/v5/market/tickers",
        {"category": "spot", "symbol": symbol},
    )
    if ticker.get("retCode") != 0:
        return False, {"error": f"tickers failed: {ticker}"}
    ticker_list = ((ticker.get("result") or {}).get("list") or [])
    if not ticker_list:
        return False, {"error": f"ticker not found: {symbol}"}
    t = ticker_list[0]

    lot = instrument.get("lotSizeFilter") or {}
    price_filter = instrument.get("priceFilter") or {}
    tick_size = Decimal(str(price_filter.get("tickSize") or "0.01"))
    min_price = Decimal(str(price_filter.get("minPrice") or "0"))
    qty_step = Decimal(str(lot.get("basePrecision") or "0.000001"))
    min_qty = Decimal(str(lot.get("minOrderQty") or qty_step))
    min_amt = Decimal(str(lot.get("minOrderAmt") or "0"))
    bid = Decimal(str(t.get("bid1Price") or "0"))
    ask = Decimal(str(t.get("ask1Price") or "0"))
    if bid <= 0 or ask <= 0:
        return False, {"error": f"invalid top-of-book for {symbol}: bid={bid} ask={ask}"}

    side = side.upper()
    if side not in {"BUY", "SELL"}:
        return False, {"error": "side must be BUY or SELL"}

    ratio = price_offset_pct / Decimal("100")
    if side == "BUY":
        raw_price = bid * (Decimal("1") - ratio)
        raw_price = raw_price if raw_price > min_price else min_price
        price = _quantize_down(raw_price, tick_size)
    else:
        raw_price = ask * (Decimal("1") + ratio)
        raw_price = raw_price if raw_price > min_price else min_price
        price = _quantize_up(raw_price, tick_size)

    qty = _quantize_up(min_qty, qty_step)
    if min_amt > 0 and price > 0:
        qty_for_min_amt = _quantize_up(min_amt / price, qty_step)
        if qty_for_min_amt > qty:
            qty = qty_for_min_amt
    if qty <= 0:
        return False, {"error": f"calculated qty is invalid: {qty}"}

    order_link_id = f"smoke-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    client = BybitRestClient(
        base_url=base_url,
        api_key=api_key,
        api_secret=api_secret,
        rsa_private_key_path=rsa_key_path,
    )

    place = await client.place_order(
        symbol=symbol,
        side="Buy" if side == "BUY" else "Sell",
        qty=_fmt_decimal(qty),
        price=_fmt_decimal(price),
        order_link_id=order_link_id,
        time_in_force="GTC",
    )
    if place.get("retCode") != 0:
        return False, {"error": f"place_order failed: {place}"}

    created = place.get("result") or {}
    order_id = created.get("orderId")
    if not order_id:
        return False, {"error": f"place_order succeeded without orderId: {place}"}

    result_payload["created"] = True
    result_payload["order_id"] = order_id
    result_payload["order_link_id"] = order_link_id
    result_payload["price"] = _fmt_decimal(price)
    result_payload["qty"] = _fmt_decimal(qty)
    result_payload["side"] = side

    # Verify order appears in open orders.
    open_orders = await client.get_open_orders(symbol=symbol)
    if open_orders.get("retCode") != 0:
        return False, {"error": f"get_open_orders failed after create: {open_orders}", **result_payload}
    open_list = ((open_orders.get("result") or {}).get("list") or [])
    found = any((o.get("orderId") == order_id) or (o.get("orderLinkId") == order_link_id) for o in open_list)
    result_payload["found_in_open_orders"] = found
    if not found:
        return False, {"error": "created order not found in open orders", **result_payload}

    # Cleanup logic.
    should_cancel = cancel_created_order or (not keep_order_open)
    result_payload["cleanup_mode"] = "cancel" if should_cancel else "keep_open"
    if should_cancel:
        cancel = await client.cancel_order(symbol=symbol, order_id=order_id, order_link_id=order_link_id)
        if cancel.get("retCode") != 0:
            return False, {"error": f"cancel_order failed: {cancel}", **result_payload}
        result_payload["cancelled"] = True
        after_cancel = await client.get_open_orders(symbol=symbol)
        if after_cancel.get("retCode") != 0:
            return False, {"error": f"get_open_orders failed after cancel: {after_cancel}", **result_payload}
        after_list = ((after_cancel.get("result") or {}).get("list") or [])
        still_present = any((o.get("orderId") == order_id) or (o.get("orderLinkId") == order_link_id) for o in after_list)
        result_payload["found_after_cancel"] = still_present
        if still_present:
            return False, {"error": "order still present in open orders after cancel", **result_payload}
    return True, result_payload


async def _run(args: argparse.Namespace) -> int:
    summary: dict[str, Any] = {
        "ws": {"ok": False},
        "rest": {"ok": None},
    }
    print(f"[WS] host={args.ws_host} symbol={args.symbol} depth={args.ws_depth} samples={args.ws_samples}")
    try:
        samples = await _read_ws_top_of_book(
            ws_host=args.ws_host,
            symbol=args.symbol,
            depth=args.ws_depth,
            samples=args.ws_samples,
            timeout_sec=args.ws_timeout_sec,
        )
        ws_summary = _summarize(samples)
        summary["ws"] = {
            "ok": True,
            "host": args.ws_host,
            "symbol": args.symbol,
            "bid": str(ws_summary["bid"]),
            "ask": str(ws_summary["ask"]),
            "mid_avg": str(ws_summary["mid_avg"]),
            "spread_avg": str(ws_summary["spread_avg"]),
        }
        print(
            "[WS] OK "
            f"bid={ws_summary['bid']} ask={ws_summary['ask']} "
            f"avg_mid={ws_summary['mid_avg']} avg_spread={ws_summary['spread_avg']}"
        )
    except Exception as exc:
        summary["ws"] = {"ok": False, "error": str(exc)}
        print(f"[WS] FAIL {exc}")
        print(f"SMOKE_RESULT {json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
        return 2

    if args.compare_host:
        print(f"[WS-COMPARE] host={args.compare_host} symbol={args.symbol}")
        try:
            samples_b = await _read_ws_top_of_book(
                ws_host=args.compare_host,
                symbol=args.symbol,
                depth=args.ws_depth,
                samples=args.ws_samples,
                timeout_sec=args.ws_timeout_sec,
            )
            a = _summarize(samples)
            b = _summarize(samples_b)
            mid_diff_pct = (
                abs(a["mid_avg"] - b["mid_avg"]) / a["mid_avg"] * Decimal("100")
                if a["mid_avg"] > 0
                else Decimal("0")
            )
            summary["ws_compare"] = {
                "ok": True,
                "host_a": args.ws_host,
                "host_b": args.compare_host,
                "mid_avg_a": str(a["mid_avg"]),
                "mid_avg_b": str(b["mid_avg"]),
                "diff_pct": f"{mid_diff_pct:.6f}",
            }
            print(
                "[WS-COMPARE] "
                f"{args.ws_host} avg_mid={a['mid_avg']} vs {args.compare_host} avg_mid={b['mid_avg']} "
                f"diff_pct={mid_diff_pct:.6f}%"
            )
        except Exception as exc:
            summary["ws_compare"] = {"ok": False, "error": str(exc)}
            print(f"[WS-COMPARE] FAIL {exc}")
            print(f"SMOKE_RESULT {json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
            return 4

    if args.check_rest_order:
        print(
            f"[REST] host={args.rest_host} symbol={args.symbol} side={args.rest_side} "
            f"auth_mode={args.auth_mode} keep_open={args.keep_order_open} cancel={args.cancel_created_order}"
        )
        ok, payload = await _rest_order_lifecycle(
            rest_host=args.rest_host,
            symbol=args.symbol,
            side=args.rest_side,
            price_offset_pct=Decimal(str(args.price_offset_pct)),
            auth_mode=args.auth_mode,
            keep_order_open=args.keep_order_open,
            cancel_created_order=args.cancel_created_order,
        )
        summary["rest"] = {"ok": ok, **payload}
        if not ok:
            print(f"[REST] FAIL {payload.get('error', payload)}")
            print(f"SMOKE_RESULT {json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
            return 3
        print(
            "[REST] OK "
            f"order_id={payload.get('order_id')} order_link_id={payload.get('order_link_id')} "
            f"found_in_open_orders={payload.get('found_in_open_orders')} cancelled={payload.get('cancelled')}"
        )

    print(f"SMOKE_RESULT {json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
    return 0


def main() -> None:
    load_dotenv(override=False)
    parser = argparse.ArgumentParser(description="Bybit WS/REST smoke test")
    parser.add_argument("--symbol", default="BTCUSDT", help="Spot symbol, example BTCUSDT")
    parser.add_argument("--ws-host", default="stream.bybit.com", help="Public WS host")
    parser.add_argument("--compare-host", default="", help="Optional second public WS host for comparison")
    parser.add_argument("--ws-depth", type=int, default=50, help="Orderbook depth for WS topic")
    parser.add_argument("--ws-samples", type=int, default=5, help="Number of WS samples")
    parser.add_argument("--ws-timeout-sec", type=float, default=12.0, help="Timeout per WS recv")
    parser.add_argument("--check-rest-order", action="store_true", help="Create one limit order via REST")
    parser.add_argument("--rest-host", default="api-demo.bybit.com", help="REST host (demo: api-demo.bybit.com)")
    parser.add_argument("--rest-side", default="BUY", help="BUY or SELL")
    parser.add_argument("--price-offset-pct", type=float, default=30.0, help="Distance from top of book to avoid fills")
    parser.add_argument(
        "--auth-mode",
        choices=["auto", "hmac", "rsa"],
        default="auto",
        help="REST auth mode selection.",
    )
    parser.add_argument("--keep-order-open", action="store_true", help="Do not cancel the created order.")
    parser.add_argument("--cancel-created-order", action="store_true", help="Explicitly cancel the created order.")
    args = parser.parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
