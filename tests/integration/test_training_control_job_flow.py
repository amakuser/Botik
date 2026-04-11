import sqlite3
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.infra.config import Settings
from botik_app_service.main import create_app


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
                (
                    "run-futures-1",
                    "futures",
                    "futures-paper-v2",
                    "offline",
                    "completed",
                    1,
                    "2026-04-10T09:30:00Z",
                    "2026-04-10T09:40:00Z",
                ),
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


def _wait_for_job_state(client: TestClient, job_id: str, expected_state: str, *, timeout: float = 8.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/jobs/{job_id}", headers={"x-botik-session-token": "training-token"})
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] == expected_state:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for job {job_id} to reach {expected_state}.")


def test_training_control_job_completes_and_updates_models_snapshot(tmp_path: Path, monkeypatch) -> None:
    fixture_db_path = tmp_path / "models.fixture.sqlite3"
    manifest_path = tmp_path / "active_models.fixture.yaml"
    _create_models_fixture_db(fixture_db_path)
    _create_models_manifest(manifest_path)
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    settings = Settings(
        session_token="training-token",
        models_read_fixture_db_path=fixture_db_path,
        models_read_manifest_path=manifest_path,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "training-token"},
            json={"job_type": "training_control", "payload": {"scope": "futures", "interval": "1m"}},
        )
        assert start.status_code == 200
        created = start.json()
        assert created["job_type"] == "training_control"

        completed = _wait_for_job_state(client, created["job_id"], "completed")
        assert completed["progress"] == 1.0

        models = client.get("/models", headers={"x-botik-session-token": "training-token"})
        assert models.status_code == 200
        snapshot = models.json()
        assert snapshot["recent_training_runs"][0]["scope"] == "futures"
        assert snapshot["recent_training_runs"][0]["status"] == "completed"
        assert snapshot["recent_training_runs"][0]["mode"] == "controlled_fixture"


def test_training_control_job_stop_marks_job_cancelled(tmp_path: Path, monkeypatch) -> None:
    fixture_db_path = tmp_path / "models.fixture.sqlite3"
    manifest_path = tmp_path / "active_models.fixture.yaml"
    _create_models_fixture_db(fixture_db_path)
    _create_models_manifest(manifest_path)
    monkeypatch.setenv("BOTIK_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    settings = Settings(
        session_token="training-token",
        models_read_fixture_db_path=fixture_db_path,
        models_read_manifest_path=manifest_path,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        start = client.post(
            "/jobs",
            headers={"x-botik-session-token": "training-token"},
            json={"job_type": "training_control", "payload": {"scope": "futures", "interval": "1m"}},
        )
        assert start.status_code == 200
        created = start.json()
        _wait_for_job_state(client, created["job_id"], "running")

        stop = client.post(
            f"/jobs/{created['job_id']}/stop",
            headers={"x-botik-session-token": "training-token"},
            json={"reason": "test-stop"},
        )
        assert stop.status_code == 200
        assert stop.json()["state"] == "cancelled"

        models = client.get("/models", headers={"x-botik-session-token": "training-token"})
        assert models.status_code == 200
        snapshot = models.json()
        assert snapshot["recent_training_runs"][0]["status"] == "cancelled"
        assert snapshot["recent_training_runs"][0]["mode"] == "controlled_fixture"
