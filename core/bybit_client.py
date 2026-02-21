# -*- coding: utf-8 -*-
"""
Клиент Bybit (Python): REST + WebSocket.

REST (pybit HTTP): баланс, свечи (klines), выставление ордеров, позиции.
WebSocket: тикеры и свечи в реальном времени в отдельном потоке; колбэки on_ticker, on_klines.
"""
import logging
import threading
import time
from typing import Any, Callable, Optional

from strategies.base import MarketData

log = logging.getLogger("BybitClient")

try:
    from pybit.unified_trading import HTTP, WebSocket
    HAS_PYBIT = True
except ImportError:
    HAS_PYBIT = False
    HTTP = None
    WebSocket = None


class BybitClient:
    """Синхронный REST-клиент и опциональный WebSocket в фоновом потоке."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
        category: str = "linear",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category
        self._http: Any = None
        self._ws: Any = None
        self._ws_thread: Optional[threading.Thread] = None
        self._on_ticker: Optional[Callable[[MarketData], None]] = None
        self._on_klines: Optional[Callable[[str, str, list], None]] = None

    def _ensure_http(self) -> Any:
        """Создать HTTP-клиент pybit при первом обращении."""
        if not HAS_PYBIT:
            log.warning("pybit not installed; REST disabled")
            return None
        if self._http is None:
            self._http = HTTP(
                testnet=self.testnet,
                api_key=self.api_key or None,
                api_secret=self.api_secret or None,
            )
        return self._http

    # --- REST ---
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict:
        """Баланс кошелька (UNIFIED и т.д.)."""
        h = self._ensure_http()
        if not h:
            return {}
        try:
            r = h.get_wallet_balance(accountType=account_type)
            return r.get("result", {}) or {}
        except Exception as e:
            log.exception("get_wallet_balance: %s", e)
            return {}

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> list:
        """История свечей (REST). interval: '15' = 15 мин."""
        h = self._ensure_http()
        if not h:
            return []
        try:
            r = h.get_kline(
                category=self.category,
                symbol=symbol,
                interval=interval,
                limit=limit,
                start=start,
                end=end,
            )
            result = r.get("result", {})
            if result is None:
                return []
            lst = result.get("list") or []
            return list(reversed(lst))  # oldest first
        except Exception as e:
            log.exception("get_klines: %s", e)
            return []

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "Market",
        reduce_only: bool = False,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> dict:
        """Выставить ордер. side: Buy | Sell; опционально take_profit, stop_loss."""
        h = self._ensure_http()
        if not h:
            return {"retCode": -1, "retMsg": "HTTP client not available"}
        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "orderType": order_type,
                "reduceOnly": reduce_only,
            }
            if take_profit is not None:
                params["takeProfit"] = str(take_profit)
            if stop_loss is not None:
                params["stopLoss"] = str(stop_loss)
            r = h.place_order(**params)
            return r.get("result", r)
        except Exception as e:
            log.exception("place_order: %s", e)
            return {"retCode": -1, "retMsg": str(e)}

    def get_positions(self, symbol: Optional[str] = None) -> list:
        """Открытые позиции (опционально по символу)."""
        h = self._ensure_http()
        if not h:
            return []
        try:
            params = {"category": self.category}
            if symbol:
                params["symbol"] = symbol
            r = h.get_positions(**params)
            result = r.get("result", {})
            if result is None:
                return []
            return result.get("list") or []
        except Exception as e:
            log.exception("get_positions: %s", e)
            return []

    # --- WebSocket (публичные тикеры и свечи) ---
    def start_ws(
        self,
        symbols: list[str],
        timeframes: list[str],
        on_ticker: Optional[Callable[[MarketData], None]] = None,
        on_klines: Optional[Callable[[str, str, list], None]] = None,
    ) -> None:
        """
        Запустить WebSocket в фоновом потоке.
        on_ticker(market_data) — при обновлении цены; on_klines(symbol, interval, list) — при новой свече.
        timeframes: например ["15"] для 15-минуток.
        """
        if not HAS_PYBIT:
            log.warning("pybit not installed; WebSocket disabled")
            return
        self._on_ticker = on_ticker
        self._on_klines = on_klines
        self._ws_stop = False
        self._ws_thread = threading.Thread(
            target=self._ws_loop,
            args=(symbols, timeframes),
            daemon=True,
        )
        self._ws_thread.start()
        log.info("WebSocket thread started for %s", symbols)

    def _ws_loop(self, symbols: list[str], timeframes: list[str]) -> None:
        """Цикл WebSocket в потоке: подписка на тикеры и свечи, вызов колбэков."""
        if not HAS_PYBIT or not WebSocket:
            return
        try:
            self._ws = WebSocket(testnet=self.testnet, channel_type="linear")
            for sym in (symbols or ["BTCUSDT"]):
                self._ws.ticker_stream(symbol=sym, callback=self._handle_ws_message)
            for sym in (symbols or ["BTCUSDT"]):
                for tf in (timeframes or ["15"]):
                    interval = int(tf) if isinstance(tf, str) and tf.isdigit() else tf
                    self._ws.kline_stream(interval=interval, symbol=sym, callback=self._handle_kline)
            while not getattr(self, "_ws_stop", True):
                time.sleep(1)
        except Exception as e:
            log.exception("WebSocket loop: %s", e)
        finally:
            if self._ws:
                try:
                    self._ws.exit()
                except Exception:
                    pass

    def _handle_ws_message(self, msg: dict) -> None:
        """Парсинг сообщения тикера и вызов on_ticker(MarketData)."""
        try:
            data = msg.get("data", {}) or msg
            if isinstance(data, list):
                data = data[0] if data else {}
            symbol = data.get("symbol", "")
            last = data.get("lastPrice") or data.get("last_price")
            if last is None:
                return
            price = float(last)
            ts = float(data.get("ts", time.time() * 1000)) / 1000.0
            md = MarketData(symbol=symbol, timeframe="", price=price, timestamp=ts, extra={})
            if self._on_ticker:
                self._on_ticker(md)
        except Exception as e:
            log.debug("ticker parse: %s", e)

    def _handle_kline(self, msg: dict) -> None:
        """Парсинг сообщения свечи и вызов on_klines(symbol, interval, list)."""
        try:
            data = msg.get("data", msg)
            if isinstance(data, list):
                data = data[0] if data else {}
            symbol = data.get("symbol", "")
            interval = str(data.get("interval", ""))
            k = data.get("kline", data)
            if isinstance(k, list):
                klines = k
            else:
                klines = [k] if k else []
            if self._on_klines and (symbol or interval or klines):
                self._on_klines(symbol, interval, klines)
        except Exception as e:
            log.debug("kline parse: %s", e)

    def stop_ws(self) -> None:
        """Остановить WebSocket и поток."""
        self._ws_stop = True
        if self._ws:
            try:
                self._ws.exit()
            except Exception:
                pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)
