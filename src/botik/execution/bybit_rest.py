"""
REST client for Bybit Spot (demo/mainnet depending on base_url).

Features:
- HMAC (primary) and RSA signatures.
- Time synchronization with /v5/market/time (time_offset_ms).
- One automatic retry on retCode=10002 after time resync.
- Stable request signing for GET/POST payloads.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
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
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = (api_secret or "").strip()
        self.rsa_private_key_path = (rsa_private_key_path or "").strip() or None
        self.recv_window = str(recv_window)
        self._rsa_private_key = None
        self.time_offset_ms = 0

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
            query = urlencode(sorted((params or {}).items()), doseq=True)
            payload = ts + self.api_key + self.recv_window + query
            sig, sign_type = self._sign(payload)
            headers["X-BAPI-SIGN"] = sig
            headers["X-BAPI-SIGN-TYPE"] = sign_type
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=20) as resp:
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
    ) -> dict[str, Any]:
        out = await self._send(method, path, params=params, json_body=json_body)
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
    ) -> dict[str, Any]:
        body = {
            "category": "spot",
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "qty": qty,
            "price": price,
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }
        return await self._request("POST", "/v5/order/create", json_body=body)

    async def cancel_order(self, symbol: str, order_link_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"category": "spot", "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        return await self._request("POST", "/v5/order/cancel", json_body=body)

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"category": "spot"}
        if symbol:
            body["symbol"] = symbol
        return await self._request("POST", "/v5/order/cancel-all", json_body=body)

    async def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": "spot"}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/v5/order/realtime", params=params)

    async def get_order(self, symbol: str, order_link_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"category": "spot", "symbol": symbol}
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
        params: dict[str, Any] = {"category": "spot", "symbol": symbol, "limit": limit}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        return await self._request("GET", "/v5/execution/list", params=params)
