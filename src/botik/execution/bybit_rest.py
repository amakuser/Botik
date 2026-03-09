"""
REST client for Bybit V5 (spot/linear depending on configured category).

Features:
- HMAC (primary) and RSA signatures.
- Time synchronization with /v5/market/time (time_offset_ms).
- One automatic retry on retCode=10002 after time resync.
- Stable request signing for GET/POST payloads.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


class BybitRestClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str | None = None,
        rsa_private_key_path: str | None = None,
        recv_window: int = 20000,
        category: str = "spot",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = (api_secret or "").strip()
        self.rsa_private_key_path = (rsa_private_key_path or "").strip() or None
        self.recv_window = str(recv_window)
        self.category = self._sanitize_category(category)
        self._rsa_private_key = None
        self.time_offset_ms = 0
        self._lot_filters: dict[str, dict[str, Decimal]] = {}

        # HMAC is the primary mode. RSA is used only if HMAC secret is not provided.
        if self.api_secret:
            self.auth_mode = "hmac"
        elif self.rsa_private_key_path:
            self.auth_mode = "rsa"
        else:
            self.auth_mode = "none"
            raise ValueError("Set api_secret (HMAC) or rsa_private_key_path (RSA) for authenticated REST requests.")

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000) + self.time_offset_ms)

    @staticmethod
    def _sanitize_category(category: str) -> str:
        value = str(category or "").strip().lower()
        if value in {"spot", "linear"}:
            return value
        return "spot"

    def _default_settle_coin(self) -> str:
        # Bot runtime currently trades USDT-quoted linear symbols.
        return "USDT"

    async def sync_server_time(self) -> int:
        """
        Sync local clock offset against Bybit server time.
        Returns current offset in milliseconds.
        """
        t0 = int(time.time() * 1000)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/v5/market/time", timeout=10) as resp:
                out = await resp.json()
        t1 = int(time.time() * 1000)
        if out.get("retCode") != 0:
            raise RuntimeError(f"time sync failed: {out}")

        result = out.get("result") or {}
        server_ms: int | None = None
        if result.get("timeNano"):
            server_ms = int(str(result["timeNano"])[:13])
        elif result.get("timeSecond"):
            server_ms = int(result["timeSecond"]) * 1000
        elif out.get("time"):
            server_ms = int(out["time"])
        if server_ms is None:
            raise RuntimeError(f"time sync response has no server timestamp: {out}")

        local_mid = (t0 + t1) // 2
        self.time_offset_ms = server_ms - local_mid
        logger.info("Bybit time sync completed: offset_ms=%s", self.time_offset_ms)
        return self.time_offset_ms

    def _sign_hmac(self, payload: str) -> str:
        return hmac.new(self.api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def _get_rsa_private_key(self):
        if self._rsa_private_key is not None:
            return self._rsa_private_key
        if not self.rsa_private_key_path:
            return None
        key_path = Path(self.rsa_private_key_path).expanduser()
        if not key_path.exists():
            raise FileNotFoundError(f"RSA private key file not found: {key_path}")
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as exc:
            raise RuntimeError("Install 'cryptography' to use BYBIT_RSA_PRIVATE_KEY_PATH.") from exc
        pem = key_path.read_bytes()
        self._rsa_private_key = serialization.load_pem_private_key(pem, password=None)
        return self._rsa_private_key

    def _sign_rsa(self, payload: str) -> str:
        key = self._get_rsa_private_key()
        if key is None:
            raise RuntimeError("RSA private key is not configured.")
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise RuntimeError("Install 'cryptography' to use BYBIT_RSA_PRIVATE_KEY_PATH.") from exc
        sig = key.sign(payload.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode("utf-8")

    def _sign(self, payload: str) -> tuple[str, str]:
        if self.auth_mode == "hmac":
            return self._sign_hmac(payload), "2"
        if self.auth_mode == "rsa":
            return self._sign_rsa(payload), "3"
        raise RuntimeError("Unknown auth mode.")

    @staticmethod
    def _fmt_decimal(value: Decimal) -> str:
        s = format(value, "f").rstrip("0").rstrip(".")
        return s or "0"

    @staticmethod
    def _quantize_down(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    @staticmethod
    def _quantize_up(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_UP) * step

    async def _get_lot_filters(self, symbol: str) -> dict[str, Decimal] | None:
        symbol_u = symbol.upper().strip()
        if not symbol_u:
            return None
        cached = self._lot_filters.get(symbol_u)
        if cached is not None:
            return cached

        out = await self._request(
            "GET",
            "/v5/market/instruments-info",
            params={"category": self.category, "symbol": symbol_u},
            retry_on_time_skew=False,
            retry_on_transport=True,
        )
        if out.get("retCode") != 0:
            logger.warning(
                "Failed to load instrument filters for %s: retCode=%s retMsg=%s",
                symbol_u,
                out.get("retCode"),
                out.get("retMsg"),
            )
            return None

        items = (out.get("result") or {}).get("list") or []
        if not items:
            logger.warning("No instrument info returned for %s", symbol_u)
            return None
        lot = (items[0] or {}).get("lotSizeFilter") or {}

        try:
            qty_step = Decimal(str(lot.get("qtyStep") or lot.get("basePrecision") or "0.000001"))
            min_qty = Decimal(str(lot.get("minOrderQty") or qty_step))
            min_amt = Decimal(str(lot.get("minOrderAmt") or lot.get("minNotionalValue") or "0"))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning("Invalid lotSizeFilter values for %s: %s", symbol_u, lot)
            return None

        if qty_step <= 0:
            qty_step = Decimal("0.000001")
        if min_qty <= 0:
            min_qty = qty_step
        if min_amt < 0:
            min_amt = Decimal("0")

        parsed = {
            "qty_step": qty_step,
            "min_qty": min_qty,
            "min_amt": min_amt,
        }
        self._lot_filters[symbol_u] = parsed
        return parsed

    async def get_symbol_min_qty(self, symbol: str) -> float | None:
        """Return exchange min tradable base quantity for the symbol."""
        filters = await self._get_lot_filters(symbol)
        if not filters:
            return None
        try:
            return float(filters["min_qty"])
        except (TypeError, ValueError, InvalidOperation):
            return None

    async def get_symbol_min_notional_quote(self, symbol: str) -> float | None:
        """Return exchange min tradable quote notional for the symbol."""
        filters = await self._get_lot_filters(symbol)
        if not filters:
            return None
        try:
            return float(filters["min_amt"])
        except (TypeError, ValueError, InvalidOperation):
            return None

    async def _normalize_order_qty(self, symbol: str, side: str, qty: str, price: str) -> str | None:
        try:
            qty_dec = Decimal(str(qty))
            price_dec = Decimal(str(price))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if qty_dec <= 0:
            return None
        side_u = side.upper().strip()

        # Remember original requested notional for inflation guard.
        original_notional = qty_dec * price_dec if price_dec > 0 else Decimal("0")

        filters = await self._get_lot_filters(symbol)
        if not filters:
            return self._fmt_decimal(qty_dec)

        qty_step = filters["qty_step"]
        min_qty = filters["min_qty"]
        min_amt = filters["min_amt"]
        spot_sell_floor_strict = self.category == "spot" and side_u == "SELL"

        if qty_dec < min_qty:
            if spot_sell_floor_strict:
                return None
            qty_dec = min_qty
        qty_dec = self._quantize_down(qty_dec, qty_step)
        if qty_dec < min_qty:
            if spot_sell_floor_strict:
                return None
            qty_dec = self._quantize_up(min_qty, qty_step)

        if min_amt > 0 and price_dec > 0 and (qty_dec * price_dec) < min_amt:
            if spot_sell_floor_strict:
                return None
            qty_dec = self._quantize_up(min_amt / price_dec, qty_step)

        if qty_dec <= 0:
            return None

        # Safety guard: reject if normalization inflated the notional by more than 3×.
        # This prevents tiny base-qty orders from being silently bumped to exchange
        # minimums that are disproportionately large relative to intended order size.
        if price_dec > 0 and original_notional > 0:
            final_notional = qty_dec * price_dec
            inflation_ratio = float(final_notional / original_notional)
            if inflation_ratio > 3.0:
                logger.warning(
                    "Order qty normalization rejected: symbol=%s side=%s "
                    "original_qty=%s normalized_qty=%s price=%s "
                    "original_notional=%.4f final_notional=%.4f inflation=%.1f×",
                    symbol, side, qty, self._fmt_decimal(qty_dec), price,
                    float(original_notional), float(final_notional), inflation_ratio,
                )
                return None

        return self._fmt_decimal(qty_dec)

    async def _send(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        ts = self._timestamp()
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": self.recv_window,
        }

        if method == "GET":
            sorted_items = sorted((params or {}).items())
            query = urlencode(sorted_items, doseq=True)
            request_url = f"{url}?{query}" if query else url
            payload = ts + self.api_key + self.recv_window + query
            sig, sign_type = self._sign(payload)
            headers["X-BAPI-SIGN"] = sig
            headers["X-BAPI-SIGN-TYPE"] = sign_type
            async with aiohttp.ClientSession() as session:
                # Send the exact same query string that was used in signature payload.
                async with session.get(request_url, headers=headers, timeout=20) as resp:
                    return await resp.json()

        body_str = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False) if json_body else "{}"
        payload = ts + self.api_key + self.recv_window + body_str
        sig, sign_type = self._sign(payload)
        headers["X-BAPI-SIGN"] = sig
        headers["X-BAPI-SIGN-TYPE"] = sign_type
        headers["Content-Type"] = "application/json"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body_str.encode("utf-8"), headers=headers, timeout=20) as resp:
                return await resp.json()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_on_time_skew: bool = True,
        retry_on_transport: bool = True,
    ) -> dict[str, Any]:
        try:
            out = await self._send(method, path, params=params, json_body=json_body)
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as exc:
            should_retry = method.upper() == "GET" and retry_on_transport
            if should_retry:
                logger.warning(
                    "Bybit transport error on %s %s: %s. Retry once.",
                    method,
                    path,
                    exc,
                )
                await asyncio.sleep(0.3)
                return await self._request(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    retry_on_time_skew=retry_on_time_skew,
                    retry_on_transport=False,
                )
            logger.warning("Bybit transport error on %s %s: %s", method, path, exc)
            return {
                "retCode": -1,
                "retMsg": f"transport_error:{type(exc).__name__}",
                "result": {},
            }

        code = out.get("retCode")
        if code == 0:
            return out

        if code == 10002 and retry_on_time_skew:
            logger.warning("Bybit time skew detected (10002). Resync and retry once.")
            try:
                await self.sync_server_time()
            except Exception as exc:
                logger.warning("Time sync failed before retry: %s", exc)
                return out
            return await self._request(
                method,
                path,
                params=params,
                json_body=json_body,
                retry_on_time_skew=False,
            )

        if code == 10004:
            logger.error("Bybit signature invalid (10004). Check key/sign mode configuration.")
        else:
            logger.warning("Bybit API error: %s", out)
        return out

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        order_link_id: str,
        time_in_force: str = "PostOnly",
        order_type: str = "Limit",
    ) -> dict[str, Any]:
        normalized_qty = await self._normalize_order_qty(symbol=symbol, side=side, qty=qty, price=price)
        if not normalized_qty:
            return {"retCode": -2, "retMsg": "invalid_qty_after_normalization", "result": {}}
        if normalized_qty != qty:
            logger.info("Order qty normalized: symbol=%s qty=%s -> %s", symbol, qty, normalized_qty)

        body: dict[str, Any] = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": normalized_qty,
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }
        # Market orders on Bybit do not accept a price field
        if order_type == "Limit":
            body["price"] = price
        return await self._request("POST", "/v5/order/create", json_body=body)

    async def cancel_order(self, symbol: str, order_link_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"category": self.category, "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        return await self._request("POST", "/v5/order/cancel", json_body=body)

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"category": self.category}
        if symbol:
            body["symbol"] = symbol
        elif self.category == "linear":
            body["settleCoin"] = self._default_settle_coin()
        return await self._request("POST", "/v5/order/cancel-all", json_body=body)

    async def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        elif self.category == "linear":
            params["settleCoin"] = self._default_settle_coin()
        return await self._request("GET", "/v5/order/realtime", params=params)

    async def get_order(self, symbol: str, order_link_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": self.category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        return await self._request("GET", "/v5/order/realtime", params=params)

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        return await self._request("GET", "/v5/account/wallet-balance", params={"accountType": account_type})

    async def get_execution_list(
        self,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"category": self.category, "symbol": symbol, "limit": limit}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        return await self._request("GET", "/v5/execution/list", params=params)

    async def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        elif self.category == "linear":
            params["settleCoin"] = self._default_settle_coin()
        return await self._request("GET", "/v5/position/list", params=params)

    async def set_trading_stop(
        self,
        *,
        symbol: str,
        position_idx: int = 0,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
    ) -> dict[str, Any]:
        if self.category != "linear":
            return {"retCode": -2, "retMsg": "set_trading_stop_supported_for_linear_only", "result": {}}

        body: dict[str, Any] = {
            "category": self.category,
            "symbol": symbol,
            "positionIdx": int(position_idx),
        }
        has_any = False
        if take_profit is not None:
            body["takeProfit"] = str(float(take_profit))
            has_any = True
        if stop_loss is not None:
            body["stopLoss"] = str(float(stop_loss))
            has_any = True
        if trailing_stop is not None:
            body["trailingStop"] = str(float(trailing_stop))
            has_any = True
        if not has_any:
            return {"retCode": -2, "retMsg": "empty_protection_payload", "result": {}}
        return await self._request("POST", "/v5/position/trading-stop", json_body=body)
