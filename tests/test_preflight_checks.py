"""
Тесты для tools/preflight.py — проверка ENV-чеков и CheckResult.
Задача #14: Preflight check.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Добавляем tools/ в путь, т.к. preflight живёт там
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from preflight import (
    CheckResult,
    _sanitize_category,
    check_env_api_keys,
    check_env_telegram,
    check_env_host,
)


# ── CheckResult ───────────────────────────────────────────────────────────


def test_check_result_to_dict_contains_required_keys() -> None:
    r = CheckResult("test:check", "REQUIRED", ok=True, message="всё ок")
    d = r.to_dict()
    assert d["name"] == "test:check"
    assert d["level"] == "REQUIRED"
    assert d["ok"] is True
    assert d["message"] == "всё ок"
    assert isinstance(d["detail"], dict)


def test_check_result_detail_defaults_to_empty_dict() -> None:
    r = CheckResult("x", "INFO", ok=False, message="no")
    assert r.detail == {}


def test_check_result_detail_preserved() -> None:
    r = CheckResult("x", "INFO", ok=True, message="ok", detail={"count": 5})
    assert r.to_dict()["detail"]["count"] == 5


# ── check_env_api_keys ────────────────────────────────────────────────────


def test_env_api_keys_ok_when_both_present() -> None:
    env = {
        "BYBIT_API_KEY": "TESTKEY1234",
        "BYBIT_API_SECRET_KEY": "TESTSECRET5678",
    }
    with patch.dict(os.environ, env, clear=False):
        result = check_env_api_keys()
    assert result.ok is True
    assert result.level == "IMPORTANT"
    assert "1234" in result.message  # последние 4 символа ключа


def test_env_api_keys_fail_when_both_missing() -> None:
    env = {"BYBIT_API_KEY": "", "BYBIT_API_SECRET_KEY": ""}
    with patch.dict(os.environ, env, clear=False):
        result = check_env_api_keys()
    assert result.ok is False


def test_env_api_keys_fail_when_only_key_present() -> None:
    env = {"BYBIT_API_KEY": "SOMEKEY", "BYBIT_API_SECRET_KEY": ""}
    with patch.dict(os.environ, env, clear=False):
        result = check_env_api_keys()
    assert result.ok is False
    assert "BYBIT_API_SECRET_KEY" in result.message


def test_env_api_keys_fail_when_only_secret_present() -> None:
    env = {"BYBIT_API_KEY": "", "BYBIT_API_SECRET_KEY": "SOMESECRET"}
    with patch.dict(os.environ, env, clear=False):
        result = check_env_api_keys()
    assert result.ok is False
    assert "BYBIT_API_KEY" in result.message


# ── check_env_telegram ────────────────────────────────────────────────────


def test_env_telegram_ok_when_token_present() -> None:
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABCDE"}, clear=False):
        result = check_env_telegram()
    assert result.ok is True


def test_env_telegram_fail_when_token_missing() -> None:
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}, clear=False):
        result = check_env_telegram()
    assert result.ok is False


# ── check_env_host ────────────────────────────────────────────────────────


def test_env_host_always_ok() -> None:
    with patch.dict(os.environ, {"BYBIT_HOST": "api.bybit.com"}, clear=False):
        result = check_env_host()
    assert result.ok is True
    assert "api.bybit.com" in result.message


def test_env_host_defaults_to_demo() -> None:
    env = {k: v for k, v in os.environ.items() if k != "BYBIT_HOST"}
    with patch.dict(os.environ, env, clear=True):
        result = check_env_host()
    assert "api-demo.bybit.com" in result.message


# ── _sanitize_category ────────────────────────────────────────────────────


def test_sanitize_category_valid_values() -> None:
    assert _sanitize_category("spot") == "spot"
    assert _sanitize_category("linear") == "linear"


def test_sanitize_category_invalid_falls_back_to_spot() -> None:
    assert _sanitize_category("futures") == "spot"
    assert _sanitize_category("") == "spot"
    assert _sanitize_category(None) == "spot"  # type: ignore[arg-type]


def test_sanitize_category_case_insensitive() -> None:
    assert _sanitize_category("SPOT") == "spot"
    assert _sanitize_category("Linear") == "linear"
