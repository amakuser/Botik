"""
Retention: хранение данных 30 дней, лимит размера БД ~50GB.
Удаление старых metrics при превышении лимита; VACUUM по расписанию (не слишком часто).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def delete_old_metrics(conn, retention_days: int, table: str = "metrics_1s", ts_column: str = "ts_utc") -> int:
    """
    Удаляет записи старше retention_days из таблицы с временной меткой ts_column.
    Ожидается ISO-формат ts_utc (например 2025-01-01T00:00:00).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    cur = conn.execute(f"DELETE FROM {table} WHERE {ts_column} < ?", (cutoff,))
    conn.commit()
    deleted = cur.rowcount
    if deleted:
        logger.info("Удалено записей из %s: %d (старше %s дней)", table, deleted, retention_days)
    return deleted


def get_db_size_bytes(db_path: str | Path) -> int:
    """Размер файла БД в байтах (приблизительно; WAL не учитывается отдельно при необходимости)."""
    p = Path(db_path)
    if not p.exists():
        return 0
    return p.stat().st_size


def run_retention(
    conn,
    db_path: str | Path,
    retention_days: int = 30,
    max_size_gb: float = 50.0,
    run_vacuum: bool = True,
) -> None:
    """
    Удаляет старые metrics при превышении лимита размера БД;
    затем при необходимости выполняет VACUUM (по расписанию вызывать не чаще раза в сутки).
    """
    size_bytes = get_db_size_bytes(db_path)
    max_bytes = int(max_size_gb * 1024 * 1024 * 1024)
    if size_bytes >= max_bytes:
        deleted = delete_old_metrics(conn, retention_days)
        if deleted and run_vacuum:
            conn.execute("VACUUM")
            conn.commit()
            logger.info("VACUUM выполнен после очистки старых metrics")
    else:
        delete_old_metrics(conn, retention_days)


# --- Как проверить: вызвать run_retention(conn, "data/botik.db", retention_days=30, max_size_gb=50).
# --- Частые ошибки: вызывать VACUUM слишком часто (блокирует БД); не учитывать размер WAL при проверке лимита.
# --- Что улучшить позже: проверка размера по PRAGMA page_count * page_size; отдельная очередь на VACUUM по cron.
