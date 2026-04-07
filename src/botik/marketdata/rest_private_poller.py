"""
RestPrivatePoller — периодический опрос Bybit demo REST API для приватных данных.

Demo-аккаунт не поддерживает приватный WebSocket, поэтому используем REST polling.

Что опрашивается:
  - /v5/account/wallet-balance  → account_snapshots + spot_balances
  - /v5/order/realtime          → spot_orders (открытые ордера)
  - /v5/position/list           → (пока пропускаем — используем paper engine)

Периодичность: POLL_INTERVAL_SEC (по умолчанию 3с).

Если API ключи не настроены — работает в режиме "offline" (только paper данные).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("botik.marketdata.rest_private_poller")

POLL_INTERVAL_SEC = 3
BYBIT_HOST = os.environ.get("BYBIT_HOST", "api-demo.bybit.com")
BASE_URL = f"https://{BYBIT_HOST}"
RECV_WINDOW = "20000"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_ms() -> str:
    return str(int(time.time() * 1000))


def _sign_hmac(api_secret: str, payload: str) -> str:
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_headers(api_key: str, api_secret: str, params_str: str) -> dict[str, str]:
    ts = _ts_ms()
    sign_payload = ts + api_key + RECV_WINDOW + params_str
    signature = _sign_hmac(api_secret, sign_payload)
    return {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "Content-Type": "application/json",
    }


def _write_app_log(msg: str, channel: str = "sys") -> None:
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, recorded_at_utc) "
                "VALUES (?, 'INFO', ?, ?)",
                (channel, msg, _utc_now()),
            )
    except Exception:
        pass


class RestPrivatePoller:
    """
    Фоновая задача: опрашивает Bybit demo REST каждые POLL_INTERVAL_SEC секунд.

    Использование:
      poller = RestPrivatePoller(api_key=..., api_secret=...)
      asyncio.create_task(poller.run())

    Результаты сохраняются в БД и доступны через get_balance() / get_orders().
    Если ключи не заданы — работает в offline-режиме (ничего не делает).
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        category: str = "spot",
    ) -> None:
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.category = category
        self._running = True
        self._last_balance: dict[str, Any] = {}
        self._last_orders: list[dict] = []
        self._online = bool(self.api_key and self.api_secret)

        if not self._online:
            log.info("RestPrivatePoller: API ключи не заданы — offline режим")

    # ── Public API ────────────────────────────────────────────

    async def run(self) -> None:
        """Запускает фоновый polling цикл."""
        if not self._online:
            return

        log.info("RestPrivatePoller: start polling %s (interval=%ds)", BASE_URL, POLL_INTERVAL_SEC)
        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:
                log.warning("RestPrivatePoller: poll error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_SEC)

    def stop(self) -> None:
        self._running = False

    def get_balance(self) -> dict[str, Any]:
        """Последний снимок баланса (из памяти)."""
        return self._last_balance

    def get_orders(self) -> list[dict]:
        """Последние открытые ордера (из памяти)."""
        return self._last_orders

    # ── Polling ───────────────────────────────────────────────

    async def _poll_once(self) -> None:
        """Один цикл опроса."""
        try:
            import aiohttp
        except ImportError:
            log.error("aiohttp не установлен: pip install aiohttp")
            self.stop()
            return

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(
                self._poll_wallet(session),
                self._poll_orders(session),
                return_exceptions=True,
            )

    async def _poll_wallet(self, session) -> None:
        """GET /v5/account/wallet-balance."""
        params = {"accountType": "UNIFIED"}
        params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        headers = _build_headers(self.api_key, self.api_secret, params_str)
        url = f"{BASE_URL}/v5/account/wallet-balance"

        try:
            import aiohttp
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
        except Exception as exc:
            log.debug("wallet poll failed: %s", exc)
            return

        if data.get("retCode") != 0:
            log.debug("wallet retCode=%s: %s", data.get("retCode"), data.get("retMsg"))
            return

        result = data.get("result", {})
        list_ = result.get("list", [])
        if not list_:
            return

        account = list_[0]
        total_equity = float(account.get("totalEquity") or 0)
        total_wallet = float(account.get("totalWalletBalance") or 0)
        unrealized = float(account.get("totalPerpUPL") or 0)
        account_type = account.get("accountType", "UNIFIED")

        self._last_balance = {
            "account_type": account_type,
            "total_equity": total_equity,
            "total_wallet": total_wallet,
            "unrealized_pnl": unrealized,
        }

        # Сохраняем в account_snapshots
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            now = _utc_now()
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO account_snapshots
                      (account_type, total_equity, wallet_balance, unrealized_pnl,
                       recorded_at_utc)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (account_type, total_equity, total_wallet, unrealized, now),
                )

                # Обновляем spot_balances по каждому активу
                coins = account.get("coin", [])
                for coin in coins:
                    asset = coin.get("coin", "")
                    if not asset:
                        continue
                    free_qty = float(coin.get("availableToWithdraw") or coin.get("free") or 0)
                    locked_qty = float(coin.get("locked") or 0)
                    total_qty = float(coin.get("walletBalance") or 0)

                    conn.execute(
                        """
                        INSERT INTO spot_balances
                          (account_type, asset, free_qty, locked_qty, total_qty,
                           source_of_truth, created_at_utc, updated_at_utc)
                        VALUES (?, ?, ?, ?, ?, 'REST', ?, ?)
                        ON CONFLICT(account_type, asset) DO UPDATE SET
                          free_qty=excluded.free_qty,
                          locked_qty=excluded.locked_qty,
                          total_qty=excluded.total_qty,
                          source_of_truth='REST',
                          updated_at_utc=excluded.updated_at_utc
                        """,
                        (account_type, asset, free_qty, locked_qty, total_qty, now, now),
                    )
        except Exception as exc:
            log.debug("wallet DB save error: %s", exc)

    async def _poll_orders(self, session) -> None:
        """GET /v5/order/realtime — открытые ордера."""
        params = {"category": self.category, "settleCoin": "USDT", "limit": "50"}
        params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        headers = _build_headers(self.api_key, self.api_secret, params_str)
        url = f"{BASE_URL}/v5/order/realtime"

        try:
            import aiohttp
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
        except Exception as exc:
            log.debug("orders poll failed: %s", exc)
            return

        if data.get("retCode") != 0:
            return

        orders = data.get("result", {}).get("list", [])
        self._last_orders = orders

        if not orders:
            return

        try:
            from src.botik.storage.db import get_db
            db = get_db()
            now = _utc_now()
            with db.connect() as conn:
                for o in orders:
                    order_id = o.get("orderId", "")
                    link_id = o.get("orderLinkId") or order_id
                    sym = o.get("symbol", "")
                    side = o.get("side", "")
                    price = float(o.get("price") or 0)
                    qty = float(o.get("qty") or 0)
                    filled_qty = float(o.get("cumExecQty") or 0)
                    status = o.get("orderStatus", "")
                    order_type = o.get("orderType", "")

                    conn.execute(
                        """
                        INSERT INTO spot_orders
                          (account_type, symbol, order_id, order_link_id, side, order_type,
                           price, qty, filled_qty, status, created_at_utc, updated_at_utc)
                        VALUES ('DEMO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(order_link_id) DO UPDATE SET
                          filled_qty=excluded.filled_qty,
                          status=excluded.status,
                          updated_at_utc=excluded.updated_at_utc
                        """,
                        (sym, order_id, link_id, side, order_type,
                         price, qty, filled_qty, status, now, now),
                    )
        except Exception as exc:
            log.debug("orders DB save error: %s", exc)
