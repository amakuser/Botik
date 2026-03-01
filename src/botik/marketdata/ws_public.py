"""
Public Spot orderbook websocket client.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from src.botik.state.state import OrderBookAggregate, TradingState, compute_imbalance

logger = logging.getLogger(__name__)

BYBIT_WS_SPOT_ORDERBOOK_TOPIC = "orderbook.{depth}.{symbol}"


def _apply_delta(book: dict[float, float], updates: list[list[str]]) -> None:
    for price_str, size_str in updates:
        price = float(price_str)
        size = float(size_str)
        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size


def _book_to_sorted_list(book: dict[float, float], descending: bool) -> list[tuple[float, float]]:
    return sorted(book.items(), key=lambda x: x[0], reverse=descending)


def aggregate_from_book(
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    tick_size: float,
    top_n: int = 10,
) -> OrderBookAggregate | None:
    if not bids or not asks:
        return None

    best_bid, best_bid_size = bids[0]
    best_ask, best_ask_size = asks[0]
    mid = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    spread_ticks = int(round(spread / tick_size)) if tick_size > 0 else 0
    imb = compute_imbalance(bids, asks, top_n)

    return OrderBookAggregate(
        symbol=symbol,
        best_bid=best_bid,
        best_ask=best_ask,
        best_bid_size=best_bid_size,
        best_ask_size=best_ask_size,
        mid=mid,
        spread_ticks=spread_ticks,
        imbalance_top_n=imb,
        ts_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


class BybitSpotOrderbookWS:
    def __init__(
        self,
        ws_host: str,
        symbols: list[str],
        depth: int,
        state: TradingState,
        tick_size: float = 0.01,
    ):
        self.ws_host = ws_host
        self.symbols = symbols
        self.depth = depth
        self.state = state
        self.tick_size = tick_size
        self._bids: dict[str, dict[float, float]] = {s: {} for s in symbols}
        self._asks: dict[str, dict[float, float]] = {s: {} for s in symbols}
        self._ws: WebSocketClientProtocol | None = None
        self._running = False

    def _url(self) -> str:
        return f"wss://{self.ws_host}/v5/public/spot"

    def _subscribe_message(self) -> dict[str, Any]:
        args = [f"orderbook.{self.depth}.{s}" for s in self.symbols]
        return {"op": "subscribe", "args": args}

    def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to decode WS JSON: %s", raw[:200])
            return

        if "topic" not in msg or "data" not in msg:
            return
        topic = msg.get("topic", "")
        if not topic.startswith("orderbook."):
            return

        data = msg.get("data", {})
        symbol = data.get("s", "")
        if symbol not in self.symbols:
            return

        bids_raw = data.get("b", [])
        asks_raw = data.get("a", [])
        if msg.get("type", "delta") == "snapshot":
            self._bids[symbol] = {float(p): float(s) for p, s in bids_raw}
            self._asks[symbol] = {float(p): float(s) for p, s in asks_raw}
        else:
            _apply_delta(self._bids[symbol], bids_raw)
            _apply_delta(self._asks[symbol], asks_raw)

        bids_list = _book_to_sorted_list(self._bids[symbol], descending=True)
        asks_list = _book_to_sorted_list(self._asks[symbol], descending=False)
        agg = aggregate_from_book(symbol, bids_list, asks_list, self.tick_size, top_n=min(10, self.depth))
        if agg is not None:
            self.state.set_orderbook(symbol, agg)

    async def run(self) -> None:
        backoff_sec = 1.0
        max_backoff = 60.0
        self._running = True

        while self._running:
            try:
                async with websockets.connect(
                    self._url(),
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    backoff_sec = 1.0
                    logger.info("WebSocket connected: %s", self._url())
                    await ws.send(json.dumps(self._subscribe_message()))
                    async for raw in ws:
                        if not self._running:
                            break
                        self._handle_message(raw)
            except Exception as exc:
                logger.warning("WebSocket reconnect in %.1fs: %s", backoff_sec, exc)
            finally:
                self._ws = None

            if not self._running:
                break

            await asyncio.sleep(backoff_sec)
            backoff_sec = min(backoff_sec * 2, max_backoff)

    def stop(self) -> None:
        self._running = False
        if self._ws:
            asyncio.create_task(self._ws.close())
