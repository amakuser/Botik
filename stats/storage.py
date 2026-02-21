# -*- coding: utf-8 -*-
"""
Хранилище статистики (Python): SQLite.

Таблицы: trades (сделки), daily_summary (дневные сводки), strategy_params (параметры от ML).
Используется RuleEngine для лимитов и ML для обучения по истории.
"""
import sqlite3
import time
from pathlib import Path
from typing import Any, List, Optional

_log = __import__("logging").getLogger("stats.storage")


def _get_conn(db_path: str) -> sqlite3.Connection:
    """Подключение к SQLite; создаём каталог при необходимости."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Создать таблицы, если их ещё нет."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL,
            pnl REAL,
            opened_at REAL NOT NULL,
            closed_at REAL,
            extra TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            pnl REAL NOT NULL DEFAULT 0,
            trade_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS strategy_params (
            strategy_id TEXT NOT NULL,
            param_key TEXT NOT NULL,
            param_value TEXT,
            updated_at REAL,
            PRIMARY KEY (strategy_id, param_key)
        );
    """)
    conn.commit()


def record_trade(
    db_path: str,
    symbol: str,
    strategy_id: str,
    side: str,
    qty: float,
    price: Optional[float] = None,
    pnl: Optional[float] = None,
    extra: Optional[dict] = None,
) -> int:
    """Записать сделку в БД; вернуть id строки."""
    conn = _get_conn(db_path)
    try:
        init_schema(conn)
        now = time.time()
        cur = conn.execute(
            """INSERT INTO trades (symbol, strategy_id, side, qty, price, pnl, opened_at, closed_at, extra)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, strategy_id, side, qty, price, pnl, now, now if pnl is not None else None, str(extra) if extra else None),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_today_pnl(db_path: str, timezone: str = "UTC") -> float:
    """Сумма PnL за текущий день (дата по UTC в SQLite)."""
    conn = _get_conn(db_path)
    try:
        init_schema(conn)
        # Use UTC date: date(timestamp, 'unixepoch')
        row = conn.execute(
            """SELECT COALESCE(SUM(pnl), 0) AS s FROM trades
               WHERE date(opened_at, 'unixepoch') = date('now') AND pnl IS NOT NULL"""
        ).fetchone()
        return float(row["s"] or 0)
    finally:
        conn.close()


def get_today_trade_count(db_path: str) -> int:
    """Количество сделок за сегодня (UTC)."""
    conn = _get_conn(db_path)
    try:
        init_schema(conn)
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM trades WHERE date(opened_at, 'unixepoch') = date('now')"""
        ).fetchone()
        return int(row["c"] or 0)
    finally:
        conn.close()


def get_trades_for_ml(db_path: str, limit: int = 10000) -> List[dict]:
    """Последние закрытые сделки с PnL для фичей ML (и для RuleEngine win rate)."""
    conn = _get_conn(db_path)
    try:
        init_schema(conn)
        rows = conn.execute(
            """SELECT id, symbol, strategy_id, side, qty, price, pnl, opened_at, closed_at, extra
               FROM trades WHERE pnl IS NOT NULL ORDER BY closed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_strategy_param(db_path: str, strategy_id: str, param_key: str, param_value: Any) -> None:
    """Сохранить/обновить параметр стратегии (например после переобучения ML)."""
    conn = _get_conn(db_path)
    try:
        init_schema(conn)
        conn.execute(
            """INSERT INTO strategy_params (strategy_id, param_key, param_value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(strategy_id, param_key) DO UPDATE SET param_value=?, updated_at=?""",
            (strategy_id, param_key, str(param_value), time.time(), str(param_value), time.time()),
        )
        conn.commit()
    finally:
        conn.close()
