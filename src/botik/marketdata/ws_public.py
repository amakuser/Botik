"""
Public Bybit orderbook websocket client (spot/linear).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from src.botik.state.state import OrderBookAggregate, PublicTradeEvent, TradingState, compute_imbalance

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


def _infer_tick_size(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    fallback: float,
) -> float:
    """
    Estimate symbol tick size from current orderbook levels.
    """
    diffs: list[float] = []
    for levels in (bids[:25], asks[:25]):
        for idx in range(1, len(levels)):
            diff = abs(levels[idx - 1][0] - levels[idx][0])
            if diff > 0:
                diffs.append(diff)
    if not diffs:
        return max(fallback, 1e-12)
    return max(min(diffs), 1e-12)


def aggregate_from_book(
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    tick_size: float,
    top_n: int = 10,
    ts_ms: int | None = None,
) -> OrderBookAggregate | None:
    if not bids or not asks:
        return None

    best_bid, best_bid_size = bids[0]
    best_ask, best_ask_size = asks[0]
    mid = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    spread_ticks = int(round(spread / tick_size)) if tick_size > 0 else 0
    imb = compute_imbalance(bids, asks, top_n)

    now_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
    return OrderBookAggregate(
        symbol=symbol,
        best_bid=best_bid,
        best_ask=best_ask,
        best_bid_size=best_bid_size,
        best_ask_size=best_ask_size,
        mid=mid,
        spread_ticks=spread_ticks,
        imbalance_top_n=imb,
        ts_ms=now_ms,
        ts_utc=datetime.fromtimestamp(now_ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


class BybitPublicOrderbookWS:
    def __init__(
        self,
        ws_host: str,
        symbols: list[str],
        depth: int,
        state: TradingState,
        tick_size: float = 0.01,
        category: str = "spot",
    ):
        self.ws_host = ws_host
        self.symbols = self._normalize_symbols(symbols)
        self.depth = depth
        self.state = state
        self.tick_size = tick_size
        self.category = self._sanitize_category(category)
        self._bids: dict[str, dict[float, float]] = {s: {} for s in self.symbols}
        self._asks: dict[str, dict[float, float]] = {s: {} for s in self.symbols}
        self._ws: WebSocketClientProtocol | None = None
        self._running = False
        self._send_lock = asyncio.Lock()
        self._max_topics_per_request = 10

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in symbols:
            s = str(raw).strip().upper()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    @staticmethod
    def _sanitize_category(category: str) -> str:
        value = str(category or "").strip().lower()
        if value in {"spot", "linear"}:
            return value
        return "spot"

    def _url(self) -> str:
        return f"wss://{self.ws_host}/v5/public/{self.category}"

    def _topics_for_symbols(self, symbols: list[str]) -> list[str]:
        topics: list[str] = []
        topics.extend(f"orderbook.{self.depth}.{s}" for s in symbols)
        topics.extend(f"publicTrade.{s}" for s in symbols)
        return topics

    def _topic_batches(self, topics: list[str]) -> list[list[str]]:
        step = max(self._max_topics_per_request, 1)
        return [topics[i : i + step] for i in range(0, len(topics), step)]

    async def _subscribe_symbols_batched(self, symbols: list[str]) -> None:
        if not symbols:
            return
        topics = self._topics_for_symbols(symbols)
        for batch in self._topic_batches(topics):
            await self._send_json({"op": "subscribe", "args": batch})
            await asyncio.sleep(0.05)

    async def _unsubscribe_topics_batched(self, topics: list[str]) -> None:
        if not topics:
            return
        for batch in self._topic_batches(topics):
            await self._send_json({"op": "unsubscribe", "args": batch})
            await asyncio.sleep(0.05)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            return
        async with self._send_lock:
            await self._ws.send(json.dumps(payload))

    def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to decode WS JSON: %s", raw[:200])
            return

        if msg.get("op") in {"subscribe", "unsubscribe"}:
            if msg.get("success", False):
                logger.info("WS %s ack: %s", msg.get("op"), msg)
            else:
                logger.warning("WS %s error: %s", msg.get("op"), msg)
            return

        if "topic" not in msg or "data" not in msg:
            return
        topic = msg.get("topic", "")
        if topic.startswith("publicTrade."):
            symbol_from_topic = topic.split(".", 1)[1] if "." in topic else ""
            rows = msg.get("data") or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                symbol = str(row.get("s") or symbol_from_topic or "").upper().strip()
                if symbol not in self._bids:
                    continue
                ts_ms = int(row.get("T") or msg.get("ts") or int(time.time() * 1000))
                event = PublicTradeEvent(
                    symbol=symbol,
                    trade_id=str(row.get("i") or ""),
                    seq=int(row.get("seq") or 0),
                    ts_ms=ts_ms,
                    taker_side=str(row.get("S") or ""),
                    price=float(row.get("p") or 0.0),
                    qty=float(row.get("v") or 0.0),
                )
                if event.price > 0 and event.qty > 0:
                    self.state.record_public_trade(event)
            return

        if not topic.startswith("orderbook."):
            return

        data = msg.get("data", {})
        symbol = data.get("s", "")
        if symbol not in self._bids:
            return

        bids_raw = data.get("b", [])
        asks_raw = data.get("a", [])
        is_snapshot = msg.get("type", "delta") == "snapshot"
        if is_snapshot:
            self._bids[symbol] = {float(p): float(s) for p, s in bids_raw}
            self._asks[symbol] = {float(p): float(s) for p, s in asks_raw}
        else:
            _apply_delta(self._bids[symbol], bids_raw)
            _apply_delta(self._asks[symbol], asks_raw)

        bids_list = _book_to_sorted_list(self._bids[symbol], descending=True)
        asks_list = _book_to_sorted_list(self._asks[symbol], descending=False)
        effective_tick_size = _infer_tick_size(bids_list, asks_list, fallback=self.tick_size)
        ts_ms = int(msg.get("ts") or int(time.time() * 1000))
        agg = aggregate_from_book(
            symbol,
            bids_list,
            asks_list,
            effective_tick_size,
            top_n=min(10, self.depth),
            ts_ms=ts_ms,
        )
        if agg is not None:
            self.state.set_orderbook(
                symbol,
                agg,
                bids=bids_list,
                asks=asks_list,
                is_snapshot=is_snapshot,
                tick_size=effective_tick_size,
            )

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
                    await self._subscribe_symbols_batched(self.symbols)
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

    async def update_symbols(self, symbols: list[str]) -> bool:
        """
        Dynamically update subscribed symbols without full process restart.
        """
        new_symbols = self._normalize_symbols(symbols)
        old_symbols = list(self.symbols)
        old_set = set(old_symbols)
        new_set = set(new_symbols)
        if not new_set or new_set == old_set:
            return False

        self.symbols = new_symbols
        for s in new_set - old_set:
            self._bids[s] = {}
            self._asks[s] = {}
        for s in old_set - new_set:
            self._bids.pop(s, None)
            self._asks.pop(s, None)
            self.state.orderbooks.pop(s, None)

        added_symbols = list(new_set - old_set)
        removed_symbols = list(old_set - new_set)
        unsub_args = self._topics_for_symbols(removed_symbols)
        try:
            if added_symbols:
                await self._subscribe_symbols_batched(added_symbols)
            if unsub_args:
                await self._unsubscribe_topics_batched(unsub_args)
        except Exception as exc:
            logger.warning("WS symbol update failed: %s", exc)

        logger.info(
            "WS universe updated: old=%s new=%s added=%s removed=%s",
            len(old_set),
            len(new_set),
            len(added_symbols),
            len(unsub_args),
        )
        return True


# Backward compatibility alias.
BybitSpotOrderbookWS = BybitPublicOrderbookWS
