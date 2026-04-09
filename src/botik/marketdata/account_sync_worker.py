"""
AccountSyncWorker — однократная или фоновая синхронизация приватных данных аккаунта Bybit.

Синхронизирует:
  - /v5/execution/list (spot)    → spot_fills
  - /v5/execution/list (linear)  → futures_fills
  - /v5/position/list (linear)   → futures_positions
  - /v5/order/realtime (spot)    → spot_orders

Использует urllib.request (stdlib only), HMAC-SHA256 подписание.
Не конкурирует с RestPrivatePoller — опрашивает другие endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("botik.account_sync")

BYBIT_HOST  = os.environ.get("BYBIT_HOST", "api-demo.bybit.com")
BASE_URL    = f"https://{BYBIT_HOST}"
RECV_WINDOW = "20000"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_ms() -> str:
    return str(int(time.time() * 1000))


def _sign_hmac(api_secret: str, payload: str) -> str:
    return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_headers(api_key: str, api_secret: str, params_str: str) -> dict[str, str]:
    ts = _ts_ms()
    signature = _sign_hmac(api_secret, ts + api_key + RECV_WINDOW + params_str)
    return {
        "X-BAPI-API-KEY":     api_key,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-SIGN":        signature,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
    }


def _get(api_key: str, api_secret: str, path: str, params: dict[str, str]) -> dict[str, Any] | None:
    params_str = urllib.parse.urlencode(sorted(params.items()))
    headers    = _build_headers(api_key, api_secret, params_str)
    url        = f"{BASE_URL}{path}?{params_str}"
    req        = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        log.error("HTTP %s for %s: %s", exc.code, path, exc.read().decode(errors="replace")[:300])
        return None
    except Exception as exc:
        log.error("Request error for %s: %s", path, exc)
        return None

    if data.get("retCode") != 0:
        log.warning("retCode=%s retMsg=%s path=%s", data.get("retCode"), data.get("retMsg"), path)
        return None
    return data


def _f(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class AccountSyncWorker:
    """
    Синхронизирует приватные данные аккаунта из Bybit в локальную БД.

    Использование:
        worker = AccountSyncWorker(api_key=..., api_secret=...)
        worker.run_once()                          # разовый sync
        worker.start_background(interval_sec=300)  # фоновый поток
        worker.stop()                              # остановить фоновый поток
    """

    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        self.api_key    = (api_key    or os.environ.get("BYBIT_API_KEY",    "")).strip()
        self.api_secret = (api_secret or os.environ.get("BYBIT_API_SECRET", "")).strip()
        self._running   = False
        self._thread: threading.Thread | None = None
        self._online    = bool(self.api_key and self.api_secret)
        if not self._online:
            log.info("AccountSyncWorker: API ключи не заданы — offline режим")

    # ── Public API ────────────────────────────────────────────

    def run_once(self) -> None:
        if not self._online:
            log.info("AccountSyncWorker.run_once: offline, пропуск")
            return
        log.info("AccountSyncWorker: начало sync")
        self._sync_spot_fills()
        self._sync_futures_fills()
        self._sync_futures_positions()
        self._sync_spot_orders()
        log.info("AccountSyncWorker: sync завершён")

    def start_background(self, interval_sec: int = 300) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, args=(interval_sec,),
            daemon=True, name="account-sync-worker",
        )
        self._thread.start()
        log.info("AccountSyncWorker: фоновый поток запущен (interval=%ds)", interval_sec)

    def stop(self) -> None:
        self._running = False

    # ── Private ───────────────────────────────────────────────

    def _loop(self, interval_sec: int) -> None:
        while self._running:
            try:
                self.run_once()
            except Exception as exc:
                log.warning("AccountSyncWorker: ошибка в цикле: %s", exc)
            for _ in range(interval_sec):
                if not self._running:
                    break
                time.sleep(1)

    def _sync_spot_fills(self) -> None:
        """GET /v5/execution/list?category=spot → spot_fills."""
        data = _get(self.api_key, self.api_secret, "/v5/execution/list", {"category": "spot", "limit": "100"})
        if data is None:
            return
        items = (data.get("result") or {}).get("list") or []
        if not items:
            return
        try:
            from src.botik.storage.db import get_db
            now = _utc_now()
            with get_db().connect() as conn:
                for f in items:
                    exec_id = str(f.get("execId") or "")
                    symbol  = str(f.get("symbol") or "")
                    if not exec_id or not symbol:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO spot_fills "
                        "(exec_id, order_id, order_link_id, symbol, side, exec_price, exec_qty, "
                        " exec_fee, fee_currency, is_maker, exec_time_ms, recorded_at_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            exec_id,
                            str(f.get("orderId") or ""),
                            str(f.get("orderLinkId") or f.get("orderId") or ""),
                            symbol,
                            str(f.get("side") or ""),
                            _f(f.get("execPrice")) or 0.0,
                            _f(f.get("execQty")) or 0.0,
                            _f(f.get("execFee")),
                            str(f.get("feeCurrency") or "USDT"),
                            1 if f.get("isMaker") else 0,
                            _i(f.get("execTime")),
                            now,
                        ),
                    )
            log.debug("spot_fills: %d записей", len(items))
        except Exception as exc:
            log.error("_sync_spot_fills DB error: %s", exc)

    def _sync_futures_fills(self) -> None:
        """GET /v5/execution/list?category=linear → futures_fills."""
        data = _get(self.api_key, self.api_secret, "/v5/execution/list", {"category": "linear", "limit": "100"})
        if data is None:
            return
        items = (data.get("result") or {}).get("list") or []
        if not items:
            return
        try:
            from src.botik.storage.db import get_db
            now = _utc_now()
            with get_db().connect() as conn:
                for f in items:
                    exec_id = str(f.get("execId") or "")
                    symbol  = str(f.get("symbol") or "")
                    if not exec_id or not symbol:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO futures_fills "
                        "(exec_id, order_link_id, symbol, side, exec_price, exec_qty, "
                        " exec_fee, fee_rate, is_maker, exec_time_ms, closed_pnl, recorded_at_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            exec_id,
                            str(f.get("orderLinkId") or f.get("orderId") or ""),
                            symbol,
                            str(f.get("side") or ""),
                            _f(f.get("execPrice")) or 0.0,
                            _f(f.get("execQty")) or 0.0,
                            _f(f.get("execFee")),
                            _f(f.get("feeRate")),
                            1 if f.get("isMaker") else 0,
                            _i(f.get("execTime")),
                            _f(f.get("closedPnl")),
                            now,
                        ),
                    )
            log.debug("futures_fills: %d записей", len(items))
        except Exception as exc:
            log.error("_sync_futures_fills DB error: %s", exc)

    def _sync_futures_positions(self) -> None:
        """GET /v5/position/list?category=linear → futures_positions."""
        data = _get(self.api_key, self.api_secret, "/v5/position/list",
                    {"category": "linear", "settleCoin": "USDT"})
        if data is None:
            return
        items = (data.get("result") or {}).get("list") or []
        if not items:
            return
        try:
            from src.botik.storage.db import get_db
            now = _utc_now()
            with get_db().connect() as conn:
                for p in items:
                    symbol = str(p.get("symbol") or "")
                    side   = str(p.get("side")   or "")
                    size   = _f(p.get("size")) or 0.0
                    if not symbol or not side:
                        continue
                    conn.execute(
                        "INSERT INTO futures_positions "
                        "(account_type, symbol, side, size, entry_price, mark_price, leverage, "
                        " liq_price, unrealised_pnl, protection_status, updated_at_utc, created_at_utc) "
                        "VALUES ('DEMO',?,?,?,?,?,?,?,?,'unprotected',?,?) "
                        "ON CONFLICT(account_type, symbol, side) DO UPDATE SET "
                        "  size=excluded.size, entry_price=excluded.entry_price, "
                        "  mark_price=excluded.mark_price, leverage=excluded.leverage, "
                        "  liq_price=excluded.liq_price, unrealised_pnl=excluded.unrealised_pnl, "
                        "  updated_at_utc=excluded.updated_at_utc",
                        (
                            symbol, side, size,
                            _f(p.get("avgPrice") or p.get("entryPrice")),
                            _f(p.get("markPrice")),
                            _f(p.get("leverage")),
                            _f(p.get("liqPrice")),
                            _f(p.get("unrealisedPnl")) or 0.0,
                            now, now,
                        ),
                    )
            log.debug("futures_positions: %d записей", len(items))
        except Exception as exc:
            log.error("_sync_futures_positions DB error: %s", exc)

    def _sync_spot_orders(self) -> None:
        """GET /v5/order/realtime?category=spot → spot_orders."""
        data = _get(self.api_key, self.api_secret, "/v5/order/realtime", {"category": "spot"})
        if data is None:
            return
        items = (data.get("result") or {}).get("list") or []
        if not items:
            return
        try:
            from src.botik.storage.db import get_db
            now = _utc_now()
            with get_db().connect() as conn:
                for o in items:
                    symbol    = str(o.get("symbol") or "")
                    link_id   = str(o.get("orderLinkId") or o.get("orderId") or "")
                    if not symbol or not link_id:
                        continue
                    conn.execute(
                        "INSERT INTO spot_orders "
                        "(account_type, symbol, order_id, order_link_id, side, order_type, "
                        " price, qty, filled_qty, status, created_at_utc, updated_at_utc) "
                        "VALUES ('DEMO',?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(order_link_id) DO UPDATE SET "
                        "  filled_qty=excluded.filled_qty, status=excluded.status, "
                        "  updated_at_utc=excluded.updated_at_utc",
                        (
                            symbol,
                            str(o.get("orderId") or ""),
                            link_id,
                            str(o.get("side") or ""),
                            str(o.get("orderType") or ""),
                            _f(o.get("price")) or 0.0,
                            _f(o.get("qty")) or 0.0,
                            _f(o.get("cumExecQty")) or 0.0,
                            str(o.get("orderStatus") or ""),
                            now, now,
                        ),
                    )
            log.debug("spot_orders: %d записей", len(items))
        except Exception as exc:
            log.error("_sync_spot_orders DB error: %s", exc)
