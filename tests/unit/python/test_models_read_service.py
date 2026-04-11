import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.models_read.service import ModelsReadService


def _create_models_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT UNIQUE NOT NULL,
                path_or_payload TEXT,
                metrics_json TEXT,
                created_at_utc TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            );
            CREATE TABLE ml_training_runs (
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
            """
        )
        connection.executemany(
            """
            INSERT INTO model_registry (model_id, path_or_payload, metrics_json, created_at_utc, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "spot-champion-v3",
                    "data/models/spot-champion-v3.pkl",
                    '{"instrument":"spot","policy":"hybrid","source_mode":"executed","status":"ready","quality_score":0.81}',
                    "2026-04-10T08:00:00Z",
                    1,
                ),
                (
                    "spot-challenger-v4",
                    "data/models/spot-challenger-v4.pkl",
                    '{"instrument":"spot","policy":"model","source_mode":"paper","status":"candidate","quality_score":0.87}',
                    "2026-04-11T10:00:00Z",
                    0,
                ),
                (
                    "futures-paper-v2",
                    "data/models/futures-paper-v2.pkl",
                    '{"instrument":"futures","policy":"hard","source_mode":"paper","status":"ready","quality_score":0.74}',
                    "2026-04-11T11:00:00Z",
                    1,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO ml_training_runs (
                run_id, model_scope, model_version, mode, status, is_trained, started_at_utc, finished_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("run-futures-1", "futures", "futures-paper-v2", "online", "running", 0, "2026-04-11T09:30:00Z", ""),
                ("run-spot-1", "spot", "spot-champion-v3", "offline", "completed", 1, "2026-04-10T08:00:00Z", "2026-04-10T08:20:00Z"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _create_models_manifest(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "product: botik_dashboard",
                "active_spot_model: spot-champion-v3",
                "active_futures_model: futures-paper-v2",
                "spot_checkpoint_path: data/models/spot-champion-v3.pkl",
                "futures_checkpoint_path: data/models/futures-paper-v2.pkl",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_models_read_service_returns_fixture_snapshot(tmp_path: Path):
    fixture_db_path = tmp_path / "models.fixture.sqlite3"
    manifest_path = tmp_path / "active_models.yaml"
    _create_models_fixture_db(fixture_db_path)
    _create_models_manifest(manifest_path)

    service = ModelsReadService(
        repo_root=REPO_ROOT,
        fixture_db_path=fixture_db_path,
        manifest_path=manifest_path,
    )
    snapshot = service.snapshot()

    assert snapshot.source_mode == "fixture"
    assert snapshot.summary.total_models == 3
    assert snapshot.summary.active_declared_count == 2
    assert snapshot.summary.ready_scopes == 2
    assert snapshot.summary.recent_training_runs_count == 2
    assert snapshot.summary.latest_run_scope == "futures"
    assert snapshot.scopes[0].active_model == "spot-champion-v3"
    assert snapshot.scopes[1].active_model == "futures-paper-v2"
    assert snapshot.registry_entries[0].model_id == "futures-paper-v2"
    assert snapshot.recent_training_runs[0].run_id == "run-futures-1"
