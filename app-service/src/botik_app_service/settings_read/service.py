import os
import time
from pathlib import Path

import httpx

from botik_app_service.contracts.settings import (
    BybitTestRequest,
    BybitTestResult,
    SettingsField,
    SettingsSaveRequest,
    SettingsSaveResult,
    SettingsSnapshot,
)

_MASKED_KEYS = {
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BYBIT_MAINNET_API_KEY",
    "BYBIT_MAINNET_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
}

_FIELD_ORDER = [
    ("BYBIT_API_KEY", "Bybit Demo API Key"),
    ("BYBIT_API_SECRET", "Bybit Demo API Secret"),
    ("BYBIT_MAINNET_API_KEY", "Bybit MainNet API Key"),
    ("BYBIT_MAINNET_API_SECRET", "Bybit MainNet API Secret"),
    ("TELEGRAM_BOT_TOKEN", "Telegram Bot Token"),
    ("TELEGRAM_CHAT_ID", "Telegram Chat ID"),
    ("DB_URL", "Database URL"),
]

_BYBIT_HOSTS = {
    "demo": "https://api-demo.bybit.com",
    "mainnet": "https://api.bybit.com",
}


def _read_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _write_env_file(path: Path, data: dict[str, str]) -> None:
    lines: list[str] = []
    for key, value in data.items():
        escaped = f'"{value}"' if (" " in value or '"' in value) else value
        lines.append(f"{key}={escaped}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


class SettingsReadService:
    def __init__(self, repo_root: Path) -> None:
        self._env_path = repo_root / ".env"

    def snapshot(self) -> SettingsSnapshot:
        env_exists = self._env_path.exists()
        file_values = _read_env_file(self._env_path) if env_exists else {}

        fields: list[SettingsField] = []
        for key, label in _FIELD_ORDER:
            raw = os.getenv(key) or file_values.get(key) or ""
            masked = key in _MASKED_KEYS
            display = _mask(raw) if masked and raw else raw
            fields.append(
                SettingsField(key=key, label=label, value=display, masked=masked, present=bool(raw))
            )

        return SettingsSnapshot(
            source_mode="env_file" if env_exists else "environment",
            env_file_path=str(self._env_path),
            env_file_exists=env_exists,
            fields=fields,
        )

    def save(self, request: SettingsSaveRequest) -> SettingsSaveResult:
        updates: dict[str, str | None] = {
            "BYBIT_API_KEY": request.bybit_api_key,
            "BYBIT_API_SECRET": request.bybit_api_secret,
            "BYBIT_MAINNET_API_KEY": request.bybit_mainnet_api_key,
            "BYBIT_MAINNET_API_SECRET": request.bybit_mainnet_api_secret,
            "TELEGRAM_BOT_TOKEN": request.telegram_bot_token,
            "TELEGRAM_CHAT_ID": request.telegram_chat_id,
            "DB_URL": request.db_url,
        }
        current: dict[str, str] = {}
        if self._env_path.exists():
            current = _read_env_file(self._env_path)

        written: list[str] = []
        for key, value in updates.items():
            if value is not None:
                current[key] = value
                written.append(key)

        try:
            _write_env_file(self._env_path, current)
            return SettingsSaveResult(success=True, fields_written=written)
        except OSError as exc:
            return SettingsSaveResult(success=False, detail=str(exc), fields_written=[])

    def test_bybit(self, request: BybitTestRequest) -> BybitTestResult:
        base = _BYBIT_HOSTS.get(request.host, _BYBIT_HOSTS["demo"])
        url = f"{base}/v5/account/info"
        import hashlib
        import hmac

        ts = str(int(time.time() * 1000))
        recv_window = "5000"
        sign_payload = ts + request.api_key + recv_window
        signature = hmac.new(
            request.api_secret.encode(), sign_payload.encode(), hashlib.sha256
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": request.api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": recv_window,
        }
        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, headers=headers)
            latency_ms = (time.monotonic() - t0) * 1000
            body = resp.json()
            ret_code = body.get("retCode", -1)
            if ret_code == 0:
                return BybitTestResult(state="ok", detail="Account info retrieved", latency_ms=latency_ms)
            return BybitTestResult(
                state="error",
                detail=body.get("retMsg", f"retCode={ret_code}"),
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return BybitTestResult(state="error", detail=str(exc))
