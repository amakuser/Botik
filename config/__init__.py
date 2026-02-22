# -*- coding: utf-8 -*-
"""
Загрузка и разбор конфигурации (YAML).

Переменные окружения: BYBIT_BOT_CONFIG (путь к yaml), BYBIT_API_KEY, BYBIT_API_SECRET.
"""
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    Загрузить YAML-конфиг.
    Путь: аргумент -> env BYBIT_BOT_CONFIG -> config/config.yaml в проекте.
    Ключи API можно задать через BYBIT_API_KEY / BYBIT_API_SECRET (перезаписывают yaml).
    """
    load_dotenv(override=False)
    if path is None:
        path = os.environ.get("BYBIT_BOT_CONFIG")
    if path is None:
        base = Path(__file__).resolve().parent.parent
        path = base / "config" / "config.yaml"
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}. Copy config.example.yaml to config.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if os.environ.get("BYBIT_API_KEY"):
        data.setdefault("bybit", {})["api_key"] = os.environ["BYBIT_API_KEY"]
    if os.environ.get("BYBIT_API_SECRET"):
        data.setdefault("bybit", {})["api_secret"] = os.environ["BYBIT_API_SECRET"]
    return data


def get_daily_limits(config: dict[str, Any]) -> dict[str, Any]:
    """Дневные лимиты: max_loss (USDT), max_profit (опц.), max_trades. Дата по UTC."""
    limits = config.get("daily_limits") or {}
    return {
        "max_loss": limits.get("max_loss"),
        "max_profit": limits.get("max_profit"),
        "max_trades": limits.get("max_trades"),
    }


def get_bybit_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Настройки Bybit: api_key, api_secret, testnet, category (linear/inverse)."""
    bybit = config.get("bybit") or {}
    return {
        "api_key": bybit.get("api_key", ""),
        "api_secret": bybit.get("api_secret", ""),
        "testnet": bybit.get("testnet", True),
        "category": bybit.get("category", "linear"),
    }
