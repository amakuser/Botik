from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from botik_app_service.contracts.telegram import (
    TelegramAlertEntry,
    TelegramCommandEntry,
    TelegramConnectivityCheckResult,
    TelegramConnectivityState,
    TelegramErrorEntry,
    TelegramOpsSnapshot,
    TelegramOpsSummary,
    TelegramOpsTruncation,
)

RECENT_COMMANDS_LIMIT = 10
RECENT_ALERTS_LIMIT = 10
RECENT_ERRORS_LIMIT = 10


class LegacyTelegramOpsAdapter:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def read_snapshot(self) -> TelegramOpsSnapshot:
        raw_cfg, env_map = self._load_runtime_inputs()
        env_state = self._resolve_env_state(raw_cfg=raw_cfg, env_map=env_map)
        db_path = self._resolve_db_path()

        commands: list[TelegramCommandEntry] = []
        alerts: list[TelegramAlertEntry] = []
        errors: list[TelegramErrorEntry] = []
        commands_count = 0
        alerts_count = 0
        errors_count = 0

        if db_path.exists():
            try:
                with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2) as connection:
                    connection.row_factory = sqlite3.Row
                    commands, commands_count = self._read_recent_commands(connection)
                    alerts, alerts_count = self._read_recent_alerts(connection)
                    errors, errors_count = self._read_recent_errors(connection)
            except sqlite3.Error:
                pass

        summary = TelegramOpsSummary(
            bot_profile=env_state["bot_profile"],
            token_profile_name=env_state["token_env_name"],
            token_configured=env_state["token_configured"],
            internal_bot_disabled=env_state["disabled"],
            connectivity_state=self._classify_connectivity_state(env_state=env_state, errors=errors),
            connectivity_detail=self._connectivity_detail(env_state=env_state, errors=errors),
            allowed_chat_count=len(env_state["masked_chats"]),
            allowed_chats_masked=list(env_state["masked_chats"]),
            commands_count=commands_count,
            alerts_count=alerts_count,
            errors_count=errors_count,
            last_successful_send=(alerts[0].message if alerts else None),
            last_error=(errors[0].error if errors else None),
            startup_status=self._startup_status(env_state),
        )
        return TelegramOpsSnapshot(
            source_mode="compatibility",
            summary=summary,
            recent_commands=commands[:RECENT_COMMANDS_LIMIT],
            recent_alerts=alerts[:RECENT_ALERTS_LIMIT],
            recent_errors=errors[:RECENT_ERRORS_LIMIT],
            truncated=TelegramOpsTruncation(
                recent_commands=commands_count > RECENT_COMMANDS_LIMIT,
                recent_alerts=alerts_count > RECENT_ALERTS_LIMIT,
                recent_errors=errors_count > RECENT_ERRORS_LIMIT,
            ),
        )

    def run_connectivity_check(self) -> TelegramConnectivityCheckResult:
        raw_cfg, env_map = self._load_runtime_inputs()
        env_state = self._resolve_env_state(raw_cfg=raw_cfg, env_map=env_map)
        if env_state["disabled"]:
            return TelegramConnectivityCheckResult(
                source_mode="compatibility",
                state="disabled",
                detail="Internal Telegram controller is disabled by environment configuration.",
            )
        if not env_state["token_configured"]:
            return TelegramConnectivityCheckResult(
                source_mode="compatibility",
                state="missing_token",
                detail="Telegram bot token is not configured.",
                error="TELEGRAM_BOT_TOKEN is not configured.",
            )

        token = env_state["token"]
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        started = time.perf_counter()
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            username = str(((payload.get("result") or {}).get("username") or "")).strip() or None
            return TelegramConnectivityCheckResult(
                source_mode="compatibility",
                state="healthy",
                detail="Telegram Bot API reachable.",
                bot_username=username,
                latency_ms=latency_ms,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return TelegramConnectivityCheckResult(
                source_mode="compatibility",
                state="degraded",
                detail="Telegram Bot API returned an error response.",
                error=body or str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive network boundary
            return TelegramConnectivityCheckResult(
                source_mode="compatibility",
                state="degraded",
                detail="Telegram Bot API connectivity check failed.",
                error=str(exc),
            )

    def _read_recent_commands(self, connection: sqlite3.Connection) -> tuple[list[TelegramCommandEntry], int]:
        if not self._table_exists(connection, "telegram_commands"):
            return ([], 0)

        count_row = connection.execute("SELECT COUNT(*) AS cnt FROM telegram_commands").fetchone()
        rows = connection.execute(
            """
            SELECT chat_id, username, command, args, response_status, created_at_utc
            FROM telegram_commands
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (RECENT_COMMANDS_LIMIT,),
        ).fetchall()
        return (
            [
                TelegramCommandEntry(
                    ts=row["created_at_utc"],
                    command=str(row["command"] or "unknown"),
                    source="telegram_bot",
                    status=str(row["response_status"] or "ok"),
                    chat_id_masked=self._mask_chat_id(row["chat_id"]),
                    username=str(row["username"]) if row["username"] is not None else None,
                    args=str(row["args"]) if row["args"] is not None else None,
                )
                for row in rows
            ],
            int(count_row["cnt"] or 0) if count_row else 0,
        )

    def _read_recent_alerts(self, connection: sqlite3.Connection) -> tuple[list[TelegramAlertEntry], int]:
        if not self._table_exists(connection, "telegram_alerts"):
            return ([], 0)

        count_row = connection.execute("SELECT COUNT(*) AS cnt FROM telegram_alerts").fetchone()
        rows = connection.execute(
            """
            SELECT alert_type, message, delivered, created_at_utc
            FROM telegram_alerts
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (RECENT_ALERTS_LIMIT,),
        ).fetchall()
        return (
            [
                TelegramAlertEntry(
                    ts=row["created_at_utc"],
                    alert_type=str(row["alert_type"] or "info"),
                    message=str(row["message"] or ""),
                    delivered=bool(int(row["delivered"] or 0)),
                    source="telegram",
                    status="ok" if bool(int(row["delivered"] or 0)) else "warning",
                )
                for row in rows
            ],
            int(count_row["cnt"] or 0) if count_row else 0,
        )

    def _read_recent_errors(self, connection: sqlite3.Connection) -> tuple[list[TelegramErrorEntry], int]:
        if not self._table_exists(connection, "app_logs"):
            return ([], 0)

        count_row = connection.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM app_logs
            WHERE channel = 'telegram'
              AND UPPER(COALESCE(level, '')) IN ('ERROR', 'WARNING')
            """
        ).fetchone()
        rows = connection.execute(
            """
            SELECT level, message, created_at_utc, extra_json
            FROM app_logs
            WHERE channel = 'telegram'
              AND UPPER(COALESCE(level, '')) IN ('ERROR', 'WARNING')
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (RECENT_ERRORS_LIMIT,),
        ).fetchall()
        entries: list[TelegramErrorEntry] = []
        for row in rows:
            source = "telegram"
            extra_json = row["extra_json"]
            if extra_json:
                try:
                    extra = json.loads(str(extra_json))
                except json.JSONDecodeError:
                    extra = {}
                source = str(extra.get("source") or source)
            entries.append(
                TelegramErrorEntry(
                    ts=row["created_at_utc"],
                    error=str(row["message"] or ""),
                    source=source,
                    status="error" if str(row["level"] or "").upper() == "ERROR" else "warning",
                )
            )
        return (entries, int(count_row["cnt"] or 0) if count_row else 0)

    def _load_runtime_inputs(self) -> tuple[dict[str, object], dict[str, str]]:
        from src.botik.gui.api_helpers import _load_yaml, _read_env_map

        return _load_yaml(), _read_env_map()

    def _resolve_db_path(self) -> Path:
        from src.botik.gui.api_helpers import _load_yaml, _resolve_db_path

        return _resolve_db_path(_load_yaml())

    @staticmethod
    def _split_chat_ids(raw_value: object) -> list[str]:
        text = str(raw_value or "").strip()
        if not text:
            return []
        return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]

    @staticmethod
    def _mask_chat_id(chat_id: object) -> str | None:
        raw = str(chat_id or "").strip()
        if not raw:
            return None
        if len(raw) <= 4:
            return raw
        return f"{raw[:2]}***{raw[-2:]}"

    def _resolve_env_state(self, *, raw_cfg: dict[str, object], env_map: dict[str, str]) -> dict[str, object]:
        telegram_cfg = raw_cfg.get("telegram")
        tg_dict = telegram_cfg if isinstance(telegram_cfg, dict) else {}
        token_env_name = str(tg_dict.get("token_env") or "TELEGRAM_BOT_TOKEN")
        chat_env_name = str(tg_dict.get("chat_id_env") or "TELEGRAM_CHAT_ID")
        bot_profile = str(tg_dict.get("profile") or "default")

        token = str(os.getenv(token_env_name) or env_map.get(token_env_name) or "").strip()
        chat_ids = self._split_chat_ids(os.getenv(chat_env_name) or env_map.get(chat_env_name) or "")
        disabled = str(
            os.getenv("BOTIK_DISABLE_INTERNAL_TELEGRAM") or env_map.get("BOTIK_DISABLE_INTERNAL_TELEGRAM") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}

        return {
            "token_env_name": token_env_name,
            "chat_env_name": chat_env_name,
            "bot_profile": bot_profile,
            "token": token,
            "token_configured": bool(token),
            "masked_chats": [masked for masked in (self._mask_chat_id(value) for value in chat_ids) if masked],
            "disabled": disabled,
        }

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _startup_status(env_state: dict[str, object]) -> str:
        if bool(env_state["disabled"]):
            return "disabled_by_env"
        if not bool(env_state["token_configured"]):
            return "missing_token"
        return "configured"

    @staticmethod
    def _classify_connectivity_state(
        *,
        env_state: dict[str, object],
        errors: list[TelegramErrorEntry],
    ) -> TelegramConnectivityState:
        if bool(env_state["disabled"]):
            return "disabled"
        if not bool(env_state["token_configured"]):
            return "missing_token"
        if errors:
            return "degraded"
        return "unknown"

    @staticmethod
    def _connectivity_detail(*, env_state: dict[str, object], errors: list[TelegramErrorEntry]) -> str:
        if bool(env_state["disabled"]):
            return "Internal Telegram controller is disabled by environment configuration."
        if not bool(env_state["token_configured"]):
            return "Telegram bot token is not configured."
        if errors:
            return "Recent Telegram warnings or errors were observed."
        return "Use connectivity check to verify Telegram Bot API reachability."
