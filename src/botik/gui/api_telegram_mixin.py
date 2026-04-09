"""
TelegramMixin - Telegram control-bot state, health, and workspace data.

Public API:
  get_telegram_workspace()  - status, health, commands, recent activity
  reload_telegram_status()  - refresh health and ensure control bot is running
"""
from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any

from .api_helpers import ROOT_DIR, _load_yaml, _read_env_map, _resolve_db_path

log = logging.getLogger("botik.webview")

_TELEGRAM_HEALTH_TTL_S = 20.0

TELEGRAM_AVAILABLE_COMMANDS: tuple[str, ...] = (
    "/start",
    "/help",
    "/status",
    "/balance",
    "/orders",
    "/starttrading",
    "/stoptrading",
    "/pull",
    "/restartsoft",
    "/restarthard",
)


class TelegramMixin:
    """Mixin providing Telegram workspace methods to DashboardAPI."""

    def _init_telegram(self) -> None:
        self._telegram_recent_commands: deque[dict[str, Any]] = deque(maxlen=80)
        self._telegram_recent_alerts: deque[dict[str, Any]] = deque(maxlen=80)
        self._telegram_recent_errors: deque[dict[str, Any]] = deque(maxlen=80)
        self._telegram_thread: threading.Thread | None = None
        self._telegram_stop_event: threading.Event | None = None
        self._telegram_missing_token_reported = False
        self._telegram_health_cache: dict[str, Any] = {
            "checked_monotonic": 0.0,
            "payload": {
                "handshake": "unknown",
                "ping_ms": None,
                "bot_username": None,
                "checked_at_utc": None,
                "error": None,
            },
        }
        self._start_telegram_control_if_configured()

    @staticmethod
    def _telegram_now_ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _split_chat_ids(raw_value: Any) -> list[str]:
        text = str(raw_value or "").strip()
        if not text:
            return []
        parts = text.replace(";", ",").split(",")
        return [part.strip() for part in parts if part.strip()]

    @staticmethod
    def _mask_chat_id(chat_id: Any) -> str:
        raw = str(chat_id or "").strip()
        if len(raw) <= 4:
            return raw or "-"
        return f"{raw[:2]}***{raw[-2:]}"

    def _telegram_env(self) -> dict[str, Any]:
        env = _read_env_map()
        token = str(env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chats = self._split_chat_ids(env.get("TELEGRAM_CHAT_ID") or "")
        disabled = str(env.get("BOTIK_DISABLE_INTERNAL_TELEGRAM") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return {
            "token": token,
            "chat_ids": chats,
            "disabled": disabled,
        }

    def _telegram_thread_state(self) -> str:
        env = self._telegram_env()
        if env["disabled"]:
            return "disabled_by_env"
        if not env["token"]:
            return "disabled"
        if self._telegram_thread is not None and self._telegram_thread.is_alive():
            return "running"
        return "stopped"

    def _record_telegram_command(
        self,
        *,
        command: str,
        source: str = "telegram_bot",
        status: str = "ok",
        chat_id: str | None = None,
        username: str | None = None,
        args: str | None = None,
    ) -> None:
        payload = {
            "ts": self._telegram_now_ts(),
            "command": str(command or "unknown"),
            "source": str(source or "telegram_bot"),
            "status": str(status or "ok"),
            "chat_id": str(chat_id or ""),
            "username": str(username or ""),
            "args": str(args or ""),
        }
        self._telegram_recent_commands.appendleft(payload)

        db_path = _resolve_db_path(_load_yaml())
        conn = self._db_connect(db_path)  # type: ignore[attr-defined]
        if conn is None or not self._table_exists(conn, "telegram_commands"):  # type: ignore[attr-defined]
            if conn is not None:
                conn.close()
            return
        try:
            conn.execute(
                "INSERT INTO telegram_commands (chat_id, username, command, args, response_status, created_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(chat_id or source or "telegram"),
                    str(username or ""),
                    str(command or "unknown"),
                    str(args or ""),
                    str(status or "ok"),
                    payload["ts"],
                ),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _record_telegram_alert(
        self,
        *,
        alert_type: str,
        message: str,
        delivered: bool = True,
        source: str = "telegram",
        status: str = "ok",
    ) -> None:
        payload = {
            "ts": self._telegram_now_ts(),
            "alert_type": str(alert_type or "info"),
            "message": str(message or ""),
            "delivered": bool(delivered),
            "source": str(source or "telegram"),
            "status": str(status or "ok"),
        }
        self._telegram_recent_alerts.appendleft(payload)

        db_path = _resolve_db_path(_load_yaml())
        conn = self._db_connect(db_path)  # type: ignore[attr-defined]
        if conn is not None and self._table_exists(conn, "telegram_alerts"):  # type: ignore[attr-defined]
            try:
                conn.execute(
                    "INSERT INTO telegram_alerts (alert_type, message, delivered, created_at_utc) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        payload["alert_type"],
                        payload["message"],
                        1 if delivered else 0,
                        payload["ts"],
                    ),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
        elif conn is not None:
            conn.close()

        self._write_app_log(  # type: ignore[attr-defined]
            db_path,
            channel="telegram",
            level="INFO",
            message=f"[telegram] {payload['alert_type']}: {payload['message']}",
            extra={"source": payload["source"], "status": payload["status"]},
        )

    def _record_telegram_error(
        self,
        *,
        source: str,
        error: str,
        status: str = "error",
    ) -> None:
        payload = {
            "ts": self._telegram_now_ts(),
            "error": str(error or "unknown"),
            "source": str(source or "telegram"),
            "status": str(status or "error"),
        }
        self._telegram_recent_errors.appendleft(payload)
        self._write_app_log(  # type: ignore[attr-defined]
            _resolve_db_path(_load_yaml()),
            channel="telegram",
            level="ERROR" if payload["status"] == "error" else "WARNING",
            message=f"[telegram] {payload['source']}: {payload['error']}",
            extra={"source": payload["source"], "status": payload["status"]},
        )

    def _sync_telegram_health(self, *, force: bool = False) -> dict[str, Any]:
        cached = self._telegram_health_cache
        if (not force) and (time.monotonic() - float(cached.get("checked_monotonic") or 0.0) < _TELEGRAM_HEALTH_TTL_S):
            return dict(cached.get("payload") or {})

        env = self._telegram_env()
        checked_at = self._telegram_now_ts()
        payload: dict[str, Any]
        if env["disabled"]:
            payload = {
                "handshake": "disabled_by_env",
                "ping_ms": None,
                "bot_username": None,
                "checked_at_utc": checked_at,
                "error": None,
            }
        elif not env["token"]:
            payload = {
                "handshake": "missing_token",
                "ping_ms": None,
                "bot_username": None,
                "checked_at_utc": checked_at,
                "error": "TELEGRAM_BOT_TOKEN is not configured",
            }
        else:
            try:
                t0 = time.perf_counter()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{env['token']}/getMe",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = json.loads(resp.read())
                ping_ms = round((time.perf_counter() - t0) * 1000, 1)
                if not body.get("ok"):
                    payload = {
                        "handshake": "error",
                        "ping_ms": ping_ms,
                        "bot_username": None,
                        "checked_at_utc": checked_at,
                        "error": str(body),
                    }
                else:
                    result = body.get("result") or {}
                    payload = {
                        "handshake": "ok",
                        "ping_ms": ping_ms,
                        "bot_username": result.get("username"),
                        "bot_name": result.get("first_name"),
                        "bot_id": result.get("id"),
                        "checked_at_utc": checked_at,
                        "error": None,
                    }
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                payload = {
                    "handshake": "error",
                    "ping_ms": None,
                    "bot_username": None,
                    "checked_at_utc": checked_at,
                    "error": f"HTTP {exc.code}: {body[:180]}",
                }
            except Exception as exc:
                payload = {
                    "handshake": "error",
                    "ping_ms": None,
                    "bot_username": None,
                    "checked_at_utc": checked_at,
                    "error": str(exc),
                }

        self._telegram_health_cache = {
            "checked_monotonic": time.monotonic(),
            "payload": payload,
        }
        return dict(payload)

    def _start_telegram_control_if_configured(self) -> None:
        env = self._telegram_env()
        if env["disabled"]:
            return
        token = str(env["token"] or "").strip()
        chat_ids = list(env["chat_ids"] or [])
        if not token:
            if not self._telegram_missing_token_reported:
                self._record_telegram_error(source="startup", error="configuration_missing_token", status="warning")
                self._telegram_missing_token_reported = True
            return
        self._telegram_missing_token_reported = False
        if self._telegram_thread is not None and self._telegram_thread.is_alive():
            return

        try:
            from src.botik.control.telegram_gui import GuiTelegramActions, start_gui_telegram_bot_in_thread
        except Exception as exc:
            self._record_telegram_error(source="startup_import", error=str(exc))
            return

        try:
            self._telegram_stop_event = threading.Event()
            actions = GuiTelegramActions(
                status=self.telegram_status_text,
                balance=self.telegram_balance_text,
                orders=self.telegram_orders_text,
                start_trading=self.telegram_start_trading,
                stop_trading=self.telegram_stop_trading,
                pull_updates=self.telegram_pull_updates,
                restart_soft=self.telegram_restart_soft,
                restart_hard=self.telegram_restart_hard,
                record_command=self._record_telegram_command,
                record_alert=lambda **kwargs: self._record_telegram_alert(
                    alert_type=str(kwargs.get("alert_type") or kwargs.get("source") or "activity"),
                    message=str(kwargs.get("message") or ""),
                    delivered=bool(kwargs.get("delivered", True)),
                    source=str(kwargs.get("source") or "telegram_bot"),
                    status=str(kwargs.get("status") or "ok"),
                ),
                record_error=lambda **kwargs: self._record_telegram_error(
                    source=str(kwargs.get("source") or "telegram_bot"),
                    error=str(kwargs.get("error") or "unknown"),
                    status=str(kwargs.get("status") or "error"),
                ),
            )
            self._telegram_thread = start_gui_telegram_bot_in_thread(
                token=token,
                actions=actions,
                allowed_chat_id=chat_ids[0] if chat_ids else None,
                stop_event=self._telegram_stop_event,
            )
            self._record_telegram_alert(
                alert_type="startup",
                message="telegram control bot started",
                delivered=True,
                source="telegram_dashboard",
                status="ok",
            )
            self._add_log("[telegram] control bot started", "telegram")  # type: ignore[attr-defined]
        except Exception as exc:
            self._record_telegram_error(source="startup_run", error=str(exc))

    def _git_run(self, *args: str) -> tuple[bool, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return proc.returncode == 0, output

    def _default_trading_mode(self) -> str:
        raw_cfg = _load_yaml()
        env = _read_env_map()
        market = str(
            env.get("MARKET_CATEGORY")
            or (raw_cfg.get("bybit") or {}).get("market_category")
            or (raw_cfg.get("execution") or {}).get("market_category")
            or "spot"
        ).strip().lower()
        return "futures_spike_reversal" if market in {"linear", "futures", "future"} else "spot_spread"

    def _format_telegram_status(self) -> str:
        state = self._telegram_thread_state()
        running_modes = self._running_modes()  # type: ignore[attr-defined]
        health = self._sync_telegram_health(force=False)
        return (
            "Dashboard Telegram control:\n"
            f"version={self._app_version}\n"  # type: ignore[attr-defined]
            f"telegram.thread={state}\n"
            f"telegram.handshake={health.get('handshake')}\n"
            f"telegram.ping_ms={health.get('ping_ms')}\n"
            f"trading={self._trading_state()} ({','.join(running_modes) if running_modes else 'none'})\n"  # type: ignore[attr-defined]
            f"ml.futures={self._ml_futures_process.state}\n"  # type: ignore[attr-defined]
            f"ml.spot={self._ml_spot_process.state}"  # type: ignore[attr-defined]
        )

    def telegram_status_text(self) -> str:
        return self._format_telegram_status()

    def telegram_balance_text(self) -> str:
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return "Balance: database is unavailable"
        try:
            balance = self._read_balance(conn)  # type: ignore[attr-defined]
        finally:
            conn.close()
        return (
            "Баланс:\n"
            f"equity={balance.get('balance_total')}\n"
            f"wallet={balance.get('balance_wallet')}\n"
            f"available={balance.get('balance_available')}"
        )

    def telegram_orders_text(self) -> str:
        conn = self._db_connect(_resolve_db_path(_load_yaml()))  # type: ignore[attr-defined]
        if not conn:
            return "Orders: database is unavailable"
        try:
            spot_orders = self._read_spot_orders(conn, limit=5)  # type: ignore[attr-defined]
            futures_orders = self._read_futures_orders(conn, limit=5)  # type: ignore[attr-defined]
        finally:
            conn.close()
        lines = [
            f"Spot open orders: {len(spot_orders)}",
            f"Futures open orders: {len(futures_orders)}",
        ]
        for row in futures_orders[:3]:
            lines.append(f"FUT {row.get('symbol')} {row.get('side')} qty={row.get('qty')} status={row.get('status')}")
        for row in spot_orders[:3]:
            lines.append(f"SPOT {row.get('symbol')} {row.get('side')} qty={row.get('qty')} status={row.get('status')}")
        return "\n".join(lines)

    def telegram_start_trading(self) -> str:
        mode = self._default_trading_mode()
        result = json.loads(self.start_trading(mode))  # type: ignore[attr-defined]
        if result.get("ok"):
            self._record_telegram_alert(
                alert_type="starttrading",
                message=f"start trading requested: {mode}",
                delivered=True,
                source="telegram_bot",
                status="ok",
            )
            return f"Trading started: {mode}"
        self._record_telegram_error(source="starttrading", error=str(result.get("error") or result.get("msg") or "unknown"))
        return f"Start trading failed: {result.get('error') or result.get('msg')}"

    def telegram_stop_trading(self) -> str:
        running_modes = self._running_modes()  # type: ignore[attr-defined]
        json.loads(self.stop_all_trading())  # type: ignore[attr-defined]
        self._record_telegram_alert(
            alert_type="stoptrading",
            message=f"stop trading requested: {','.join(running_modes) if running_modes else 'none'}",
            delivered=True,
            source="telegram_bot",
            status="ok",
        )
        return f"Trading stop requested for: {', '.join(running_modes) if running_modes else 'no active modes'}"

    def telegram_pull_updates(self) -> str:
        ok, status_out = self._git_run("status", "--porcelain")
        if not ok:
            self._record_telegram_error(source="pull_status", error=status_out or "git status failed")
            return f"git status failed:\n{status_out}"
        dirty = [line for line in status_out.splitlines() if line.strip()]
        if dirty:
            msg = "git pull blocked: working tree is dirty"
            self._record_telegram_error(source="pull_dirty_tree", error=msg)
            return msg
        ok, out = self._git_run("pull", "--ff-only")
        if ok:
            self._record_telegram_alert(
                alert_type="pull",
                message="git pull --ff-only completed",
                delivered=True,
                source="telegram_bot",
                status="ok",
            )
            return out or "Already up to date"
        self._record_telegram_error(source="pull_failed", error=out or "git pull failed")
        return out or "git pull failed"

    def telegram_restart_soft(self) -> str:
        stop_msg = self.telegram_stop_trading()
        start_msg = self.telegram_start_trading()
        return f"{stop_msg}\n{start_msg}"

    def telegram_restart_hard(self) -> str:
        pull_msg = self.telegram_pull_updates()
        restart_msg = self.telegram_restart_soft()
        return f"{pull_msg}\n{restart_msg}"

    def _read_recent_telegram_commands(self, conn: sqlite3.Connection | None, limit: int = 20) -> list[dict[str, Any]]:
        if conn is None or not self._table_exists(conn, "telegram_commands"):  # type: ignore[attr-defined]
            return list(self._telegram_recent_commands)[: int(limit)]
        try:
            rows = conn.execute(
                "SELECT chat_id, username, command, args, response_status, created_at_utc "
                "FROM telegram_commands ORDER BY created_at_utc DESC, id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [
                {
                    "ts": row[5],
                    "chat_id": row[0],
                    "username": row[1],
                    "command": row[2],
                    "args": row[3],
                    "status": row[4],
                    "source": "telegram_bot",
                }
                for row in rows
            ]
        except Exception:
            return list(self._telegram_recent_commands)[: int(limit)]

    def _read_recent_telegram_alerts(self, conn: sqlite3.Connection | None, limit: int = 20) -> list[dict[str, Any]]:
        if conn is None or not self._table_exists(conn, "telegram_alerts"):  # type: ignore[attr-defined]
            return list(self._telegram_recent_alerts)[: int(limit)]
        try:
            rows = conn.execute(
                "SELECT alert_type, message, delivered, created_at_utc "
                "FROM telegram_alerts ORDER BY created_at_utc DESC, id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [
                {
                    "ts": row[3],
                    "alert_type": row[0],
                    "message": row[1],
                    "delivered": bool(row[2]),
                }
                for row in rows
            ]
        except Exception:
            return list(self._telegram_recent_alerts)[: int(limit)]

    def _read_recent_telegram_errors(self, conn: sqlite3.Connection | None, limit: int = 20) -> list[dict[str, Any]]:
        if conn is None:
            return list(self._telegram_recent_errors)[: int(limit)]
        try:
            rows = self._read_app_logs(  # type: ignore[attr-defined]
                conn,
                channels=("telegram",),
                limit=max(int(limit) * 3, 30),
            )
            filtered = [
                {
                    "ts": row.get("ts"),
                    "level": row.get("level"),
                    "message": row.get("message"),
                }
                for row in rows
                if str(row.get("level") or "").upper() in {"ERROR", "WARNING"}
                or any(
                    token in str(row.get("message") or "").lower()
                    for token in ("error", "warn", "fail")
                )
            ]
            return filtered[: int(limit)] or list(self._telegram_recent_errors)[: int(limit)]
        except Exception:
            return list(self._telegram_recent_errors)[: int(limit)]

    def get_telegram_workspace(self, limit: int = 20, force_refresh: bool = False) -> str:
        self._start_telegram_control_if_configured()
        health = self._sync_telegram_health(force=force_refresh)
        env = self._telegram_env()
        db_path = _resolve_db_path(_load_yaml())
        conn = self._db_connect(db_path)  # type: ignore[attr-defined]
        try:
            commands = self._read_recent_telegram_commands(conn, limit=int(limit))
            alerts = self._read_recent_telegram_alerts(conn, limit=int(limit))
            errors = self._read_recent_telegram_errors(conn, limit=int(limit))
        finally:
            if conn:
                conn.close()

        state = self._telegram_thread_state()
        available_commands = list(TELEGRAM_AVAILABLE_COMMANDS)
        allowed_chats_masked = [self._mask_chat_id(chat_id) for chat_id in env["chat_ids"]]
        return json.dumps(
            {
                "state": state,
                "enabled": bool(env["token"]) and not bool(env["disabled"]),
                "token_configured": bool(env["token"]),
                "allowed_chats_masked": allowed_chats_masked,
                "allowed_chats_count": len(allowed_chats_masked),
                "available_commands": available_commands,
                "commands_count": len(available_commands),
                "recent_commands": commands,
                "recent_alerts": alerts,
                "recent_errors": errors,
                "recent_commands_count": len(commands),
                "recent_alerts_count": len(alerts),
                "recent_errors_count": len(errors),
                "last_command": commands[0] if commands else None,
                "last_alert": alerts[0] if alerts else None,
                "last_error": errors[0] if errors else None,
                "health": health,
                "bot_username": health.get("bot_username"),
                "handshake": health.get("handshake"),
                "ping_ms": health.get("ping_ms"),
                "checked_at_utc": health.get("checked_at_utc"),
            },
            default=str,
        )

    def reload_telegram_status(self) -> str:
        self._start_telegram_control_if_configured()
        self._record_telegram_alert(
            alert_type="reload",
            message="telegram status reloaded",
            delivered=True,
            source="dashboard",
            status="ok",
        )
        return self.get_telegram_workspace(force_refresh=True)
