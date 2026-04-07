"""
Smoke-test Botik migrations against PostgreSQL.

Usage:
    python tools/postgres_migration_smoke.py \
        --db-url postgresql://botik:botik_dev_password@127.0.0.1:54329/botik
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.botik.storage.db import POSTGRES, reset_db
from src.botik.storage.schema import bootstrap_db


DEFAULT_REQUIRED_TABLES: tuple[str, ...] = (
    "_schema_migrations",
    "account_snapshots",
    "spot_holdings",
    "futures_positions",
    "model_stats",
    "ml_training_runs",
    "telegram_commands",
)


def _wait_for_connection(db_url: str, wait_sec: float) -> str | None:
    deadline = time.time() + max(float(wait_sec), 0.0)
    last_error = ""
    while True:
        try:
            db = reset_db(db_url)
            with db.connect() as conn:
                conn.execute("SELECT 1")
            return None
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if time.time() >= deadline:
                return last_error
            time.sleep(1.0)


def _run_smoke(db_url: str, wait_sec: float, required_tables: tuple[str, ...]) -> dict[str, Any]:
    wait_error = _wait_for_connection(db_url, wait_sec)
    if wait_error:
        raise RuntimeError(f"postgres is not reachable: {wait_error}")

    db = bootstrap_db(db_url)
    if db.driver != POSTGRES:
        raise RuntimeError(f"expected PostgreSQL driver, got: {db.driver}")

    with db.connect() as conn:
        missing_tables = [table for table in required_tables if not conn.table_exists(table)]
        applied_rows = conn.execute("SELECT version FROM _schema_migrations ORDER BY version").fetchall()

    return {
        "driver": db.driver,
        "url": db.url,
        "applied_migrations": len(applied_rows),
        "missing_tables": missing_tables,
        "required_tables": list(required_tables),
        "ok": not missing_tables,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test Botik PostgreSQL migrations")
    parser.add_argument(
        "--db-url",
        required=True,
        help="PostgreSQL URL, for example postgresql://botik:botik_dev_password@127.0.0.1:54329/botik",
    )
    parser.add_argument(
        "--wait-sec",
        type=float,
        default=45.0,
        help="How long to wait for PostgreSQL to become reachable",
    )
    parser.add_argument(
        "--require-table",
        action="append",
        dest="required_tables",
        default=[],
        help="Additional table that must exist after migrations",
    )
    args = parser.parse_args()

    required_tables = DEFAULT_REQUIRED_TABLES + tuple(
        table for table in args.required_tables if str(table or "").strip()
    )

    try:
        result = _run_smoke(args.db_url, args.wait_sec, required_tables)
        if result["missing_tables"]:
            print(f"PG_MIGRATION_SMOKE_FAIL {json.dumps(result, ensure_ascii=False, sort_keys=True)}")
            raise SystemExit(2)
        print(f"PG_MIGRATION_SMOKE_OK {json.dumps(result, ensure_ascii=False, sort_keys=True)}")
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "ok": False,
            "url": args.db_url,
            "error": str(exc),
            "required_tables": list(required_tables),
        }
        print(f"PG_MIGRATION_SMOKE_FAIL {json.dumps(payload, ensure_ascii=False, sort_keys=True)}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
