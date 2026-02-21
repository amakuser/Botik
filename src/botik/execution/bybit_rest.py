"""
REST клиент Bybit Spot (DEMO: api-demo.bybit.com).
place_order / cancel / get_open_orders / get_order / get_balance.
Idempotency: orderLinkId; retries без дублей. Подпись HMAC по официальной схеме.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def _sign_get(secret: str, timestamp: str, recv_window: str, query_string: str, api_key: str) -> str:
    plain = timestamp + api_key + recv_window + query_string
    return hmac.new(secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_post(secret: str, timestamp: str, recv_window: str, json_body: str, api_key: str) -> str:
    plain = timestamp + api_key + recv_window + json_body
    return hmac.new(secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).hexdigest()


class BybitRestClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        recv_window: int = 5000,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = str(recv_window)

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    async def _request(
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
            query = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
            sig = _sign_get(self.api_secret, ts, self.recv_window, query, self.api_key)
            headers["X-BAPI-SIGN"] = sig
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    out = await resp.json()
        else:
            body_str = json.dumps(json_body) if json_body else "{}"
            sig = _sign_post(self.api_secret, ts, self.recv_window, body_str, self.api_key)
            headers["X-BAPI-SIGN"] = sig
            headers["Content-Type"] = "application/json"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body_str, headers=headers) as resp:
                    out = await resp.json()
        if out.get("retCode") != 0:
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
        """Выставить лимитный пост-онли ордер. side: Buy | Sell."""
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
        """Отменить по orderLinkId или orderId. Приоритет у orderId если оба заданы."""
        params: dict[str, Any] = {"category": "spot", "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        return await self._request("POST", "/v5/order/cancel", json_body=params)

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        """Отменить все ордера; если symbol задан — только по этому символу."""
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
        """Список исполнений (fills) по ордеру или по символу."""
        params: dict[str, Any] = {"category": "spot", "symbol": symbol, "limit": limit}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id
        return await self._request("GET", "/v5/execution/list", params=params)


# --- Как проверить: на DEMO ключах place_order с уникальным orderLinkId, затем get_open_orders, cancel.
# --- Частые ошибки: не уникальный orderLinkId; перепутать GET query string и POST body при подписи.
# --- Что улучшить позже: адаптивный polling статусов при отсутствии private WS; retry с экспоненциальной задержкой.
