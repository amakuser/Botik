from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_MODEL_VERSION = "futures-controlled-fixture-v1"
FIXTURE_PHASES: tuple[tuple[str, str], ...] = (
    ("bootstrap", "Preparing training workspace."),
    ("labeling", "Loading bounded labeled dataset."),
    ("training", "Training the bounded futures model."),
    ("evaluation", "Evaluating the bounded training result."),
    ("finalize", "Finalizing the training run."),
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


def _emit_log(level: str, message: str) -> None:
    _emit({"type": "log", "level": level.upper(), "message": message})


def _emit_progress(
    *,
    progress: float,
    message: str,
    phase: str,
    scope: str,
    interval: str,
    completed_units: int,
    total_units: int,
) -> None:
    _emit(
        {
            "type": "progress",
            "progress": progress,
            "message": message,
            "phase": phase,
            "category": scope,
            "interval": interval,
            "completed_units": completed_units,
            "total_units": total_units,
        }
    )


def _ensure_fixture_schema(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ml_training_runs (
                run_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                model_version TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                epoch INTEGER,
                max_epochs INTEGER,
                loss REAL,
                accuracy REAL,
                sharpe_ratio REAL,
                trade_count INTEGER,
                is_trained INTEGER NOT NULL DEFAULT 0,
                trained_at_utc TEXT,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS app_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _upsert_fixture_run(
    *,
    db_path: Path,
    run_id: str,
    scope: str,
    status: str,
    started_at: str,
    mode: str,
    model_version: str,
    is_trained: bool,
    notes: str,
    finished_at: str | None = None,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO ml_training_runs (
                run_id, model_scope, model_version, mode, status, epoch, max_epochs,
                accuracy, trade_count, is_trained, trained_at_utc, started_at_utc, finished_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                model_version=excluded.model_version,
                mode=excluded.mode,
                status=excluded.status,
                epoch=excluded.epoch,
                max_epochs=excluded.max_epochs,
                accuracy=excluded.accuracy,
                trade_count=excluded.trade_count,
                is_trained=excluded.is_trained,
                trained_at_utc=excluded.trained_at_utc,
                finished_at_utc=excluded.finished_at_utc,
                notes=excluded.notes
            """,
            (
                run_id,
                scope,
                model_version,
                mode,
                status,
                None,
                None,
                0.66 if is_trained else 0.0,
                2400 if is_trained else 0,
                1 if is_trained else 0,
                finished_at or "",
                started_at,
                finished_at or "",
                notes,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _write_fixture_log(db_path: Path, scope: str, level: str, message: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
            (f"ml_{scope}", level.upper(), message, _timestamp()),
        )
        connection.commit()
    finally:
        connection.close()


def _run_fixture(*, job_id: str, scope: str, interval: str, control_file: Path, fixture_db_path: Path) -> int:
    del job_id  # job_id is intentionally not persisted in the fixture DB schema.
    _ensure_fixture_schema(fixture_db_path)
    started_at = _timestamp()
    run_id = f"fixture-training-{int(time.time() * 1000)}"
    _upsert_fixture_run(
        db_path=fixture_db_path,
        run_id=run_id,
        scope=scope,
        status="running",
        started_at=started_at,
        mode="controlled_fixture",
        model_version=FIXTURE_MODEL_VERSION,
        is_trained=False,
        notes="Bounded fixture training control is running.",
    )
    _write_fixture_log(fixture_db_path, scope, "INFO", "Fixture training control started.")
    _emit_log("INFO", "Fixture futures training started.")

    total_units = len(FIXTURE_PHASES)
    for index, (phase, message) in enumerate(FIXTURE_PHASES, start=1):
        if control_file.exists():
            finished_at = _timestamp()
            _upsert_fixture_run(
                db_path=fixture_db_path,
                run_id=run_id,
                scope=scope,
                status="cancelled",
                started_at=started_at,
                mode="controlled_fixture",
                model_version=FIXTURE_MODEL_VERSION,
                is_trained=False,
                notes="Fixture training control stopped by request.",
                finished_at=finished_at,
            )
            _write_fixture_log(fixture_db_path, scope, "WARNING", "Fixture training control stopped.")
            _emit_log("WARNING", "Fixture futures training stop requested.")
            _emit_progress(
                progress=min(index / total_units, 0.95),
                message="Fixture futures training stopped.",
                phase="stopped",
                scope=scope,
                interval=interval,
                completed_units=index,
                total_units=total_units,
            )
            return 0

        _write_fixture_log(fixture_db_path, scope, "INFO", message)
        _emit_progress(
            progress=index / total_units,
            message=message,
            phase=phase,
            scope=scope,
            interval=interval,
            completed_units=index,
            total_units=total_units,
        )
        _emit_log("INFO", message)
        time.sleep(0.35)

    finished_at = _timestamp()
    _upsert_fixture_run(
        db_path=fixture_db_path,
        run_id=run_id,
        scope=scope,
        status="completed",
        started_at=started_at,
        mode="controlled_fixture",
        model_version=FIXTURE_MODEL_VERSION,
        is_trained=True,
        notes="Fixture training control completed successfully.",
        finished_at=finished_at,
    )
    _write_fixture_log(fixture_db_path, scope, "INFO", "Fixture training control completed.")
    _emit_log("INFO", "Fixture futures training completed.")
    _emit_progress(
        progress=1.0,
        message="Fixture futures training completed.",
        phase="completed",
        scope=scope,
        interval=interval,
        completed_units=total_units,
        total_units=total_units,
    )
    return 0


def _database_url() -> str:
    return os.getenv("DB_URL", "sqlite:///data/botik.db")


def _mark_compatibility_run(
    *,
    db,
    run_id: str,
    status: str,
    note: str,
) -> None:
    try:
        with db.connect() as connection:
            connection.execute(
                "UPDATE ml_training_runs SET status=?, finished_at_utc=? WHERE run_id=?",
                (status, _timestamp(), run_id),
            )
            if connection.table_exists("app_logs"):
                connection.execute(
                    "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
                    ("ml_futures", "WARNING" if status == "cancelled" else "INFO", note, _timestamp()),
                )
    except Exception:
        pass


def _run_compatibility(*, scope: str, interval: str, control_file: Path) -> int:
    from src.botik.data.process_manager import ProcessManager
    from src.botik.storage.db import Database

    db = Database(_database_url())
    manager = ProcessManager(db)
    legacy_interval = "1" if interval == "1m" else interval
    run_id = manager.start_training(scope, interval=legacy_interval)
    _emit_log("INFO", f"Legacy futures training started: run_id={run_id}")
    last_status = ""
    last_progress_emit = 0.0
    started = time.monotonic()

    while True:
        if control_file.exists():
            manager.stop(scope)
            _mark_compatibility_run(
                db=db,
                run_id=run_id,
                status="cancelled",
                note="Training control stopped the legacy futures training run.",
            )
            _emit_log("WARNING", "Legacy futures training stop requested.")
            _emit_progress(
                progress=max(last_progress_emit, 0.15),
                message="Legacy futures training stopped.",
                phase="stopped",
                scope=scope,
                interval=interval,
                completed_units=1,
                total_units=1,
            )
            return 0

        status = manager.get_status(scope)
        if status.status != last_status:
            _emit_log("INFO", f"Legacy training status: {status.status}")
            last_status = status.status

        if status.is_running:
            elapsed = time.monotonic() - started
            progress = min(0.85, 0.1 + (elapsed / 20.0))
            last_progress_emit = progress
            _emit_progress(
                progress=progress,
                message=f"Legacy futures training is {status.status}.",
                phase="training",
                scope=scope,
                interval=interval,
                completed_units=0,
                total_units=1,
            )
            time.sleep(0.5)
            continue

        if status.status == "completed":
            _emit_log("INFO", f"Legacy futures training completed: version={status.model_version}")
            _emit_progress(
                progress=1.0,
                message="Legacy futures training completed.",
                phase="completed",
                scope=scope,
                interval=interval,
                completed_units=1,
                total_units=1,
            )
            return 0

        if status.status == "failed":
            _emit_log("ERROR", "Legacy futures training failed.")
            return 1

        _emit_log("ERROR", f"Legacy futures training exited unexpectedly with status={status.status}.")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--scope", required=True, choices=["futures"])
    parser.add_argument("--interval", required=True, choices=["1m"])
    parser.add_argument("--mode", required=True, choices=["fixture", "compatibility"])
    parser.add_argument("--control-file", required=True)
    parser.add_argument("--fixture-db-path")
    parser.add_argument("--manifest-path")
    args = parser.parse_args(argv)

    control_file = Path(args.control_file)
    control_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.mode == "fixture":
            if not args.fixture_db_path:
                print("Fixture mode requires --fixture-db-path.", file=sys.stderr, flush=True)
                return 1
            return _run_fixture(
                job_id=args.job_id,
                scope=args.scope,
                interval=args.interval,
                control_file=control_file,
                fixture_db_path=Path(args.fixture_db_path),
            )
        return _run_compatibility(scope=args.scope, interval=args.interval, control_file=control_file)
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
