"""
TickerMixin — Live price ticker via Bybit public WebSocket.

Public API:
  get_live_tickers()  — JSON with price + 24h change for watched symbols
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time

log = logging.getLogger("botik.webview")

_DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
)

# How old a cached price may be before it is flagged as stale
_STALE_THRESHOLD_MS: int = 30_000  # 30 seconds


class TickerMixin:
    """Mixin that subscribes to Bybit tickers WS and caches live prices."""

    def _init_ticker(self) -> None:
        """Initialise state and start background WS thread.

        Must be called from DashboardAPI.__init__.
        """
        self._ticker_cache: dict[str, dict] = {}
        self._ticker_lock = threading.Lock()
        self._ticker_symbols: list[str] = list(_DEFAULT_SYMBOLS)
        self._ticker_stop = threading.Event()
        threading.Thread(
            target=self._ticker_ws_loop, daemon=True, name="ticker-ws"
        ).start()

    # ── Background thread ────────────────────────────────────────────────────

    def _ticker_ws_loop(self) -> None:
        """Entry point for the background daemon thread."""
        backoff = 2.0
        while not self._ticker_stop.is_set():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._ticker_ws_task())
                backoff = 2.0
            except Exception as exc:
                log.warning("[ticker] WS error, retry in %.0fs: %s", backoff, exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _ticker_ws_task(self) -> None:
        """Single WebSocket session: subscribe → receive → cache."""
        import websockets  # noqa: PLC0415 — deferred to avoid startup cost

        host = os.environ.get("BYBIT_WS_HOST", "stream.bybit.com")
        if "demo" in host.lower():
            host = "stream.bybit.com"

        url = f"wss://{host}/v5/public/linear"
        symbols = list(self._ticker_symbols)
        topics = [f"tickers.{s}" for s in symbols]

        async with websockets.connect(
            url, ping_interval=20, ping_timeout=10, close_timeout=5
        ) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": topics}))
            log.info("[ticker] connected, watching %d symbols on %s", len(symbols), host)
            async for raw in ws:
                if self._ticker_stop.is_set():
                    break
                self._handle_ticker_msg(raw)

    def _handle_ticker_msg(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        topic = msg.get("topic", "")
        if not topic.startswith("tickers."):
            return

        data = msg.get("data")
        if not data:
            return

        symbol = data.get("symbol", "")
        if not symbol:
            return

        with self._ticker_lock:
            entry = dict(self._ticker_cache.get(symbol, {}))
            # Merge: only overwrite fields present in this frame (handles deltas)
            if data.get("lastPrice"):
                entry["price"] = data["lastPrice"]
            if data.get("price24hPcnt") is not None:
                entry["change_pct"] = data["price24hPcnt"]
            if data.get("highPrice24h"):
                entry["high"] = data["highPrice24h"]
            if data.get("lowPrice24h"):
                entry["low"] = data["lowPrice24h"]
            if data.get("volume24h"):
                entry["volume"] = data["volume24h"]
            entry["symbol"] = symbol
            entry["ts"] = int(time.time() * 1000)
            self._ticker_cache[symbol] = entry

    # ── Public API ───────────────────────────────────────────────────────────

    def get_live_tickers(self) -> str:
        """Returns JSON with live prices for all watched symbols."""
        now_ms = int(time.time() * 1000)
        with self._ticker_lock:
            result = []
            for sym in self._ticker_symbols:
                entry = self._ticker_cache.get(sym)
                if entry:
                    stale = (now_ms - entry.get("ts", 0)) > _STALE_THRESHOLD_MS
                    result.append({**entry, "stale": stale})
                else:
                    result.append({
                        "symbol": sym, "price": None,
                        "change_pct": None, "stale": True,
                    })
        return json.dumps({"tickers": result})
