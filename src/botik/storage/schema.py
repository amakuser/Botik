"""
Database bootstrap: initialise the database and run all pending migrations.

Call once at application startup:
    from src.botik.storage.schema import bootstrap_db
    bootstrap_db()

After this, every part of the codebase can call get_db() to get a connection.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from src.botik.storage.db import get_db, reset_db, Database
from src.botik.storage.migrations import run_migrations

log = logging.getLogger("botik.storage.schema")


def bootstrap_db(url: str | None = None) -> Database:
    """
    Initialise database and apply all pending migrations.

    url — optional override (default: DB_URL env var or sqlite:///data/botik.db).
    Returns the Database singleton.
    """
    db = reset_db(url) if url else get_db()
    log.info("DB driver=%s  url=%s", db.driver, _safe_url(db.url))

    with db.connect() as conn:
        applied = run_migrations(conn)

    if applied:
        log.info("Database schema up to date (%d migration(s) applied)", applied)
    else:
        log.debug("Database schema up to date (no new migrations)")

    return db


def _safe_url(url: str) -> str:
    """Hide password in postgres URL for logging."""
    if "@" in url:
        scheme, rest = url.split("://", 1)
        userinfo, host = rest.split("@", 1)
        if ":" in userinfo:
            user, _ = userinfo.split(":", 1)
            return f"{scheme}://{user}:***@{host}"
    return url
