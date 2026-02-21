"""
Вспомогательные функции времени (UTC ISO для БД и логов).
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Текущее время UTC в формате ISO для записи в БД."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
