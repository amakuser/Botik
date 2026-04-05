"""
SettingsMixin — load/save settings, Bybit API check, DB check, Telegram test.

Public API: load_settings, save_settings, test_bybit_api, check_db,
            send_telegram_test, run_preflight, reload_config.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
import time
from typing import Any

from .api_helpers import (
    CONFIG_PATH, ENV_PATH, ROOT_DIR,
    _load_yaml, _read_env_map, _resolve_db_path,
)

log = logging.getLogger("botik.webview")


class SettingsMixin:
    """Mixin providing settings management methods to DashboardAPI."""

    # Keys written to / read from .env (order defines file section)
    _SETTINGS_KEYS = (
        "BYBIT_API_KEY", "BYBIT_API_SECRET_KEY",
        "BYBIT_MAINNET_API_KEY", "BYBIT_MAINNET_API_SECRET",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "DB_URL",
        "EXEC_MODE", "BYBIT_HOST", "MARKET_CATEGORY",
        # Futures strategy params (% values stored as percent, e.g. 1.0 = 1%)
        "FUTURES_BALANCE", "FUTURES_RISK_PCT", "FUTURES_ATR_SL_MULT",
        "FUTURES_ATR_TP_MULT", "FUTURES_MAX_POS_PCT", "FUTURES_HOLD_TIMEOUT_H",
        "FUTURES_SPIKE_BPS", "FUTURES_MAX_POSITIONS",
        "FUTURES_SYMBOLS",
        # Spot strategy params
        "SPOT_BALANCE", "SPOT_RISK_PCT", "SPOT_ATR_SL_MULT",
        "SPOT_ATR_TP_MULT", "SPOT_MAX_POS_PCT", "SPOT_HOLD_TIMEOUT_H",
        "SPOT_SPIKE_BPS",
        "SPOT_SYMBOLS",
    )

    # Fallback aliases: some .env files use different names for the same key
    _ENV_ALIASES: dict[str, tuple[str, ...]] = {
        "BYBIT_API_SECRET_KEY": ("BYBIT_API_SECRET",),
        "EXEC_MODE":            ("EXECUTION_MODE",),
        "BYBIT_HOST":           ("BYBIT_API_HOST", "BYBIT_BASE_URL"),
    }

    # ── Settings load / save ──────────────────────────────────

    def load_settings(self) -> str:
        """Returns JSON with current values from .env and bot_settings DB."""
        env = _read_env_map()
        log.info("[settings] load_settings: ENV_PATH=%s  found_keys=%s", ENV_PATH, list(env.keys()))
        values: dict[str, str] = {}
        for k in self._SETTINGS_KEYS:
            val = env.get(k, "")
            if not val:
                for alias in self._ENV_ALIASES.get(k, ()):
                    val = env.get(alias, "")
                    if val:
                        break
            values[k] = val
        log.info("[settings] loaded: %s", {k: bool(v) for k, v in values.items()})

        # Overlay DB bot_settings (may have keys not in .env)
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                rows = conn.execute("SELECT key, value FROM bot_settings").fetchall()
                for row in rows:
                    r = dict(row)
                    k, v = r.get("key", ""), r.get("value", "")
                    if k in self._SETTINGS_KEYS:
                        values[k] = v or values.get(k, "")
        except Exception as exc:
            log.debug("load_settings db read skipped: %s", exc)

        return json.dumps({"ok": True, "values": values, "env_path": str(ENV_PATH)})

    def save_settings(self, data: dict) -> str:
        """Saves settings to .env file and bot_settings DB table."""
        if not isinstance(data, dict):
            return json.dumps({"ok": False, "error": "invalid data"})

        # ── 1. Write / update .env ────────────────────────────
        env_map = _read_env_map()
        for k in self._SETTINGS_KEYS:
            if k in data:
                env_map[k] = str(data[k])

        if ENV_PATH.exists():
            try:
                lines_out: list[str] = []
                with open(ENV_PATH, encoding="utf-8") as fh:
                    for line in fh:
                        stripped = line.strip()
                        if "=" in stripped and not stripped.startswith("#"):
                            k, _, _ = stripped.partition("=")
                            k = k.strip()
                            if k in env_map:
                                lines_out.append(f"{k}={env_map.pop(k)}\n")
                                continue
                        lines_out.append(line if line.endswith("\n") else line + "\n")
                for k, v in env_map.items():
                    lines_out.append(f"{k}={v}\n")
                with open(ENV_PATH, "w", encoding="utf-8") as fh:
                    fh.writelines(lines_out)
            except Exception as exc:
                return json.dumps({"ok": False, "error": f".env write error: {exc}"})
        else:
            try:
                with open(ENV_PATH, "w", encoding="utf-8") as fh:
                    for k, v in env_map.items():
                        fh.write(f"{k}={v}\n")
            except Exception as exc:
                return json.dumps({"ok": False, "error": f".env create error: {exc}"})

        # ── 2. Save to bot_settings DB ────────────────────────
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                for k in self._SETTINGS_KEYS:
                    if k in data:
                        conn.execute(
                            "INSERT INTO bot_settings (key, value, updated_at_utc)"
                            " VALUES (?, ?, CURRENT_TIMESTAMP)"
                            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                            " updated_at_utc=CURRENT_TIMESTAMP",
                            (k, str(data[k])),
                        )
        except Exception as exc:
            log.warning("save_settings db write skipped: %s", exc)

        self._add_log("[sys] settings saved", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": True})

    # ── API checks ────────────────────────────────────────────

    def test_bybit_api(self, host: str, key: str, secret: str) -> str:
        """Check Bybit API keys via GET /v5/account/wallet-balance (stdlib only)."""
        import urllib.error
        import urllib.request

        host   = str(host   or "api-demo.bybit.com").strip().rstrip("/")
        key    = str(key    or "").strip()
        secret = str(secret or "").strip()
        if not key or not secret:
            return json.dumps({"ok": False, "error": "API Key или Secret не заданы"})
        try:
            ts          = str(int(time.time() * 1000))
            recv_window = "5000"
            params      = "accountType=UNIFIED"
            sign_str    = ts + key + recv_window + params
            sig         = hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
            url         = f"https://{host}/v5/account/wallet-balance?{params}"
            req         = urllib.request.Request(url, headers={
                "X-BAPI-API-KEY":     key,
                "X-BAPI-TIMESTAMP":   ts,
                "X-BAPI-SIGN":        sig,
                "X-BAPI-RECV-WINDOW": recv_window,
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
            if body.get("retCode") != 0:
                return json.dumps({"ok": False, "error": f"retCode={body.get('retCode')} {body.get('retMsg','')}"})
            coins: list[dict] = []
            for acc in (body.get("result") or {}).get("list") or []:
                for coin in acc.get("coin") or []:
                    if float(coin.get("walletBalance") or 0) > 0:
                        coins.append({
                            "coin":    coin.get("coin"),
                            "balance": coin.get("walletBalance"),
                            "usdValue": coin.get("usdValue"),
                        })
            total_eq = (body.get("result", {}).get("list") or [{}])[0].get("totalEquity", "—")
            log.info("[bybit] test_api OK host=%s total_equity=%s", host, total_eq)
            return json.dumps({"ok": True, "total_equity": total_eq, "coins": coins[:8]})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            return json.dumps({"ok": False, "error": f"HTTP {exc.code}: {body[:200]}"})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    def check_db(self) -> str:
        """Return DB file size, ping, and row counts for key tables."""
        db_path = _resolve_db_path(_load_yaml())
        result: dict[str, Any] = {"path": str(db_path)}
        try:
            result["size_mb"] = round(db_path.stat().st_size / 1024 / 1024, 2)
        except Exception:
            result["size_mb"] = None
        try:
            t0   = time.perf_counter()
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.execute("SELECT 1").fetchone()
            result["ping_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            tables = [
                "price_history", "spot_holdings", "spot_orders",
                "futures_positions", "futures_paper_trades",
                "outcomes", "ml_training_runs", "model_stats",
                "app_logs", "bot_settings",
            ]
            counts: list[dict] = []
            for tbl in tables:
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    counts.append({"table": tbl, "rows": n})
                except Exception:
                    pass
            conn.close()
            result["counts"] = counts
            result["ok"]     = True
        except Exception as exc:
            result["ok"]    = False
            result["error"] = str(exc)
        return json.dumps(result, default=str)

    def send_telegram_test(self) -> str:
        """Send a real test message via Telegram Bot API."""
        import urllib.error
        import urllib.request

        env     = _read_env_map()
        token   = env.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
        if not token:
            return json.dumps({"ok": False, "error": "TELEGRAM_BOT_TOKEN не задан в .env"})
        if not chat_id:
            return json.dumps({"ok": False, "error": "TELEGRAM_CHAT_ID не задан в .env"})
        try:
            text    = f"✅ Botik Dashboard — тест соединения\nВерсия: {self._app_version}"  # type: ignore[attr-defined]
            url     = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req     = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                if body.get("ok"):
                    log.info("[telegram] test send OK chat_id=%s", chat_id)
                    self._add_log(f"[telegram] test send OK → chat {chat_id}", "telegram")  # type: ignore[attr-defined]
                    return json.dumps({"ok": True, "msg": "Сообщение отправлено"})
                return json.dumps({"ok": False, "error": str(body)})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            log.warning("[telegram] test send HTTP error %s: %s", exc.code, body)
            return json.dumps({"ok": False, "error": f"HTTP {exc.code}: {body}"})
        except Exception as exc:
            log.warning("[telegram] test send failed: %s", exc)
            return json.dumps({"ok": False, "error": str(exc)})

    # ── Misc ops ──────────────────────────────────────────────

    def run_preflight(self) -> str:
        """Runs a quick preflight diagnostics check."""
        import webview
        checks: list[dict] = [
            {"name": "Config",   "ok": CONFIG_PATH.exists(),
             "detail": str(CONFIG_PATH) if CONFIG_PATH.exists() else "not found"},
        ]
        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        checks.append({"name": "Database", "ok": db_path.exists(),
                        "detail": str(db_path) if db_path.exists() else "not found"})
        import sys
        checks.append({"name": "Python",    "ok": True, "detail": sys.version.split()[0]})
        checks.append({"name": "pywebview", "ok": True, "detail": getattr(webview, "__version__", "installed")})

        all_ok = all(c["ok"] for c in checks)
        self._add_log(f"[sys] preflight {'OK' if all_ok else 'WARN'}", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": all_ok, "checks": checks})

    def reload_config(self) -> str:
        """Reloads config from disk (no restart needed)."""
        raw_cfg = _load_yaml()
        mode    = str((raw_cfg.get("execution") or {}).get("mode") or "paper")
        self._add_log(f"[sys] config reloaded mode={mode}", "sys")  # type: ignore[attr-defined]
        return json.dumps({"ok": True, "mode": mode})
