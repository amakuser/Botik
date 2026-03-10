"""
Paper execution adapter with BybitRestClient-like interface.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from src.botik.state.state import TradingState


class PaperTradingClient:
    def __init__(self, state: TradingState, fill_on_cross: bool = True, category: str = "spot") -> None:
        self.state = state
        self.fill_on_cross = fill_on_cross
        self.category = str(category or "spot").strip().lower() or "spot"
        self.auth_mode = "paper"
        self.recv_window = "paper"
        self.capabilities: dict[str, bool] = {
            "reconciliation": False,
            "protection": False,
            "wallet_balance": True,
            "positions": False,
            "trading_stop": False,
        }
        self.supports_reconciliation = False
        self.supports_protection = False
        self._open_orders: dict[str, dict[str, Any]] = {}
        self._executions: list[dict[str, Any]] = []

    def _new_order_id(self) -> str:
        return f"paper-{int(time.time() * 1000)}-{uuid.uuid4().hex[:10]}"

    def _is_marketable(self, symbol: str, side: str, price: float) -> bool:
        ob = self.state.get_orderbook(symbol)
        if ob is None:
            return False
        if side == "Buy":
            return price >= ob.best_ask
        return price <= ob.best_bid

    def _record_execution(self, order: dict[str, Any]) -> None:
        self._executions.append(
            {
                "symbol": order["symbol"],
                "side": order["side"],
                "orderId": order["orderId"],
                "orderLinkId": order["orderLinkId"],
                "execId": f"paper-exec-{uuid.uuid4().hex[:12]}",
                "execQty": order["qty"],
                "execPrice": order["price"],
                "execFee": "0",
                "feeCurrency": "USDT",
            }
        )

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
        order_id = self._new_order_id()
        normalized_order_type = str(order_type or "Limit").strip().title()
        if normalized_order_type not in {"Limit", "Market"}:
            normalized_order_type = "Limit"
        order = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "orderId": order_id,
            "orderLinkId": order_link_id,
            "timeInForce": time_in_force,
            "orderType": normalized_order_type,
        }

        marketable = normalized_order_type == "Market" or (
            self.fill_on_cross and self._is_marketable(symbol, side, float(price or 0.0))
        )
        if marketable and (time_in_force != "PostOnly" or normalized_order_type == "Market"):
            self._record_execution(order)
        else:
            self._open_orders[order_id] = order

        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": order_id,
                "orderLinkId": order_link_id,
            },
        }

    async def cancel_order(self, symbol: str, order_link_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
        target_id = order_id
        if target_id is None and order_link_id:
            for oid, order in self._open_orders.items():
                if order.get("orderLinkId") == order_link_id and order.get("symbol") == symbol:
                    target_id = oid
                    break
        if target_id and target_id in self._open_orders:
            self._open_orders.pop(target_id, None)
        return {"retCode": 0, "retMsg": "OK", "result": {}}

    async def cancel_all_orders(self, symbol: str | None = None) -> dict[str, Any]:
        if symbol is None:
            self._open_orders.clear()
        else:
            to_delete = [oid for oid, order in self._open_orders.items() if order.get("symbol") == symbol]
            for oid in to_delete:
                self._open_orders.pop(oid, None)
        return {"retCode": 0, "retMsg": "OK", "result": {}}

    async def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        if symbol:
            out = [o for o in self._open_orders.values() if o.get("symbol") == symbol]
        else:
            out = list(self._open_orders.values())
        return {"retCode": 0, "retMsg": "OK", "result": {"list": out}}

    async def get_execution_list(
        self,
        symbol: str,
        order_id: str | None = None,
        order_link_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        items = [e for e in self._executions if e.get("symbol") == symbol]
        if order_id:
            items = [e for e in items if e.get("orderId") == order_id]
        if order_link_id:
            items = [e for e in items if e.get("orderLinkId") == order_link_id]
        return {"retCode": 0, "retMsg": "OK", "result": {"list": items[-limit:]}}

    async def get_symbol_min_qty(self, symbol: str) -> float | None:
        # Paper mode has no exchange filters; caller falls back to config floor.
        return None

    async def get_symbol_min_notional_quote(self, symbol: str) -> float | None:
        # Paper mode has no real exchange filters.
        return None

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        # Provide a deterministic virtual wallet response for non-trading read paths.
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "accountType": str(account_type),
                        "coin": [
                            {
                                "coin": "USDT",
                                "walletBalance": "10000",
                                "equity": "10000",
                                "free": "10000",
                                "availableToWithdraw": "10000",
                            }
                        ],
                    }
                ]
            },
        }

    async def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        return {
            "retCode": -2,
            "retMsg": "positions_api_unsupported_in_paper",
            "result": {"list": []},
        }

    async def set_trading_stop(
        self,
        *,
        symbol: str,
        position_idx: int = 0,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
    ) -> dict[str, Any]:
        return {
            "retCode": -2,
            "retMsg": "set_trading_stop_unsupported_in_paper",
            "result": {},
        }
