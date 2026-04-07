"""
BalanceMixin — background balance poller for Bybit demo/live account.

Starts a daemon thread in _init_balance() that polls
GET /v5/account/wallet-balance every 30 s and writes results into the
account_snapshots SQLite table.  _read_balance() in SpotMixin then picks
up the latest row automatically.

Requires: no extra dependencies — uses stdlib urllib + hmac only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .api_helpers import _load_yaml, _read_env_map, _resolve_db_path
from .event_bus import bus as _event_bus

log = logging.getLogger("botik.webview")

_POLL_INTERVAL = 30          # seconds between balance polls
_REQUEST_TIMEOUT = 10        # HTTP timeout
_RECV_WINDOW = "5000"
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BalanceMixin:
    """
    Mixin that polls Bybit wallet balance in a background thread and
    persists it to account_snapshots so get_snapshot() shows real data.

    Must call self._init_balance() from DashboardAPI.__init__.
    """

    def _init_balance(self) -> None:
        """Initialise state and start background poller thread."""
        self._balance_stop = threading.Event()
        threading.Thread(
            target=self._balance_poll_loop, daemon=True, name="balance-poll"
        ).start()
        log.info("[balance] poller started (interval=%ds)", _POLL_INTERVAL)

    # ── Background thread ─────────────────────────────────────────────────────

    def _balance_poll_loop(self) -> None:
        """Poll balance on startup and then every _POLL_INTERVAL seconds."""
        while not self._balance_stop.is_set():
            try:
                self._poll_balance_once()
            except Exception as exc:
                log.warning("[balance] poll error: %s", exc)
            self._balance_stop.wait(_POLL_INTERVAL)

    def _poll_balance_once(self) -> None:
        """Single poll: fetch balance from Bybit REST → write to DB."""
        env = _read_env_map()

        key = env.get("BYBIT_API_KEY", "").strip()
        secret = (
            env.get("BYBIT_API_SECRET_KEY", "")
            or env.get("BYBIT_API_SECRET", "")
        ).strip()
        host = env.get("BYBIT_HOST", "api-demo.bybit.com").strip().rstrip("/")

        if not key or not secret:
            return  # no credentials yet — skip silently

        ts          = str(int(time.time() * 1000))
        params      = "accountType=UNIFIED"
        sign_str    = ts + key + _RECV_WINDOW + params
        sig         = hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
        url         = f"https://{host}/v5/account/wallet-balance?{params}"

        req = urllib.request.Request(url, headers={
            "X-BAPI-API-KEY":     key,
            "X-BAPI-TIMESTAMP":   ts,
            "X-BAPI-SIGN":        sig,
            "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
        })

        try:
            with _NO_PROXY.open(req, timeout=_REQUEST_TIMEOUT) as resp:
                body: dict = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            log.warning("[balance] HTTP %d from %s", exc.code, host)
            return
        except Exception as exc:
            log.warning("[balance] request failed: %s", exc)
            return

        if body.get("retCode") != 0:
            log.warning("[balance] API error: retCode=%s %s",
                        body.get("retCode"), body.get("retMsg", ""))
            return

        accounts: list[dict] = (body.get("result") or {}).get("list") or []
        if not accounts:
            return

        acc = accounts[0]
        total_equity       = float(acc.get("totalEquity")        or 0)
        wallet_balance     = float(acc.get("totalWalletBalance") or 0)
        available_balance  = float(acc.get("totalAvailableBalance") or acc.get("totalMarginBalance") or 0)

        self._write_balance_snapshot(total_equity, wallet_balance, available_balance)
        log.debug("[balance] equity=%.2f  wallet=%.2f  available=%.2f",
                  total_equity, wallet_balance, available_balance)
        # Push balance event reactively (T40)
        _event_bus.emit("balance_update", {
            "total_equity":      total_equity,
            "wallet_balance":    wallet_balance,
            "available_balance": available_balance,
        })

    def _write_balance_snapshot(
        self,
        total_equity: float,
        wallet_balance: float,
        available_balance: float,
    ) -> None:
        """Insert one row into account_snapshots (matches core_store schema)."""
        import uuid
        import json as _json
        try:
            db_path = _resolve_db_path(_load_yaml())
            now_utc    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            snap_id    = str(uuid.uuid4())
            payload    = _json.dumps({
                "total_equity":       total_equity,
                "wallet_balance":     wallet_balance,
                "available_balance":  available_balance,
                "source":             "balance_poller",
            })
            conn = sqlite3.connect(str(db_path), timeout=5)
            try:
                conn.execute(
                    "INSERT INTO account_snapshots "
                    "(snapshot_id, account_type, snapshot_kind, "
                    " total_equity, wallet_balance, available_balance, "
                    " payload_json, created_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (snap_id, "UNIFIED", "balance_poll",
                     total_equity, wallet_balance, available_balance,
                     payload, now_utc),
                )
                conn.commit()
                # Keep only the latest 1000 rows
                conn.execute(
                    "DELETE FROM account_snapshots WHERE id NOT IN "
                    "(SELECT id FROM account_snapshots ORDER BY id DESC LIMIT 1000)"
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            log.warning("[balance] DB write failed: %s", exc)
