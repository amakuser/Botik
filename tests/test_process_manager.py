"""
Tests for ProcessManager and training_worker helpers (M3).

Verifies:
- ProcessManager.is_running() → False for unknown/exited scope
- ProcessManager.get_status() → "never_run" when ml_training_runs is empty
- ProcessManager.get_status() → reads latest row correctly
- ProcessManager.start_training() raises if already running
- ProcessManager.stop() on non-running scope is a no-op
- ProcessManager.get_all_statuses() covers both scopes
- _write_run_status() upserts correctly
- _write_log() inserts into app_logs with correct channel
- _update_labeling_registry() marks symbols as ready/pending
- _deploy_if_ready() returns (False, "v0") below accuracy threshold
- _deploy_if_ready() calls registry.save() when threshold met

No real subprocesses are started — Popen is mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.data.process_manager import ProcessManager, ProcessStatus
from src.botik.data.training_worker import (
    _write_run_status,
    _write_log,
    _update_labeling_registry,
    _deploy_if_ready,
)
from src.botik.data.training_pipeline import TrainingReport, SymbolTrainingResult


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    with database.connect() as conn:
        run_migrations(conn)
    return database


@pytest.fixture()
def pm(db: Database) -> ProcessManager:
    return ProcessManager(db)


# ─────────────────────────────────────────────────────────────────────────────
#  is_running / get_status — no subprocess
# ─────────────────────────────────────────────────────────────────────────────

def test_is_running_returns_false_for_unknown_scope(pm: ProcessManager) -> None:
    assert pm.is_running("futures") is False
    assert pm.is_running("spot") is False


def test_get_status_never_run(pm: ProcessManager) -> None:
    status = pm.get_status("futures")
    assert status.scope == "futures"
    assert status.status == "never_run"
    assert status.is_running is False
    assert status.run_id is None


def test_get_status_reads_completed_run(db: Database, pm: ProcessManager) -> None:
    _write_run_status(db, "test-run-1", "futures", "completed",
                      historian_acc=0.63, predictor_acc=0.61,
                      total_samples=2400, is_trained=True, model_version="v2")

    status = pm.get_status("futures")
    assert status.run_id == "test-run-1"
    assert status.status == "completed"
    assert status.is_trained is True
    assert abs(status.historian_accuracy - 0.63) < 0.001
    assert status.model_version == "v2"


def test_get_all_statuses_covers_both_scopes(pm: ProcessManager) -> None:
    statuses = pm.get_all_statuses()
    assert "futures" in statuses
    assert "spot" in statuses
    assert all(isinstance(v, ProcessStatus) for v in statuses.values())


# ─────────────────────────────────────────────────────────────────────────────
#  start_training / stop — mocked Popen
# ─────────────────────────────────────────────────────────────────────────────

def test_start_training_returns_run_id(db: Database) -> None:
    pm = ProcessManager(db)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None   # still running
    mock_proc.pid = 9999

    with patch("src.botik.data.process_manager.subprocess.Popen", return_value=mock_proc):
        run_id = pm.start_training("futures")

    assert len(run_id) == 36   # UUID format
    assert pm.is_running("futures") is True


def test_start_training_raises_if_already_running(db: Database) -> None:
    pm = ProcessManager(db)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 9998

    with patch("src.botik.data.process_manager.subprocess.Popen", return_value=mock_proc):
        pm.start_training("futures")
        with pytest.raises(RuntimeError, match="already running"):
            pm.start_training("futures")


def test_stop_on_running_process_terminates(db: Database) -> None:
    pm = ProcessManager(db)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 1234

    with patch("src.botik.data.process_manager.subprocess.Popen", return_value=mock_proc):
        pm.start_training("futures")

    pm.stop("futures")

    mock_proc.terminate.assert_called_once()
    assert pm.is_running("futures") is False


def test_stop_on_nonrunning_scope_is_noop(pm: ProcessManager) -> None:
    pm.stop("futures")   # should not raise


def test_is_running_false_after_process_exits(db: Database) -> None:
    pm = ProcessManager(db)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # running
    mock_proc.pid = 5678

    with patch("src.botik.data.process_manager.subprocess.Popen", return_value=mock_proc):
        pm.start_training("spot")

    # Simulate process exit
    mock_proc.poll.return_value = 0
    assert pm.is_running("spot") is False


# ─────────────────────────────────────────────────────────────────────────────
#  _write_run_status
# ─────────────────────────────────────────────────────────────────────────────

def test_write_run_status_inserts_record(db: Database) -> None:
    _write_run_status(db, "run-abc", "futures", "running")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, model_scope FROM ml_training_runs WHERE run_id=?",
            ("run-abc",),
        ).fetchone()
    assert row is not None
    assert row[0] == "running"
    assert row[1] == "futures"


def test_write_run_status_upserts_on_same_run_id(db: Database) -> None:
    _write_run_status(db, "run-xyz", "spot", "running")
    _write_run_status(db, "run-xyz", "spot", "completed", historian_acc=0.65, is_trained=True)

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM ml_training_runs WHERE run_id=?", ("run-xyz",)
        ).fetchone()
        row = conn.execute(
            "SELECT status, is_trained FROM ml_training_runs WHERE run_id=?", ("run-xyz",)
        ).fetchone()

    assert rows[0] == 1           # one row, not two
    assert row[0] == "completed"
    assert row[1] == 1


# ─────────────────────────────────────────────────────────────────────────────
#  _write_log
# ─────────────────────────────────────────────────────────────────────────────

def test_write_log_inserts_into_app_logs(db: Database) -> None:
    _write_log(db, "futures", "INFO", "Training started")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT channel, level, message FROM app_logs WHERE message=?",
            ("Training started",),
        ).fetchone()
    assert row is not None
    assert row[0] == "ml_futures"
    assert row[1] == "INFO"


# ─────────────────────────────────────────────────────────────────────────────
#  _update_labeling_registry (M3.2)
# ─────────────────────────────────────────────────────────────────────────────

def test_update_labeling_registry_marks_ready(db: Database) -> None:
    from src.botik.data.symbol_labeling_registry import SymbolLabelingRegistry

    report = TrainingReport(scope="futures")
    report.results = [
        SymbolTrainingResult("BTCUSDT", "linear", "1", samples_used=1200),
        SymbolTrainingResult("ETHUSDT", "linear", "1", samples_used=0),  # no samples
    ]

    _update_labeling_registry(db, "futures", "1", report)

    reg = SymbolLabelingRegistry(db)
    btc = reg.get("BTCUSDT", "linear", "1", "futures")
    eth = reg.get("ETHUSDT", "linear", "1", "futures")

    assert btc is not None and btc.labeling_status == "ready"
    assert btc.labeled_count == 1200
    assert eth is not None and eth.labeling_status == "pending"


# ─────────────────────────────────────────────────────────────────────────────
#  _deploy_if_ready (M3.1)
# ─────────────────────────────────────────────────────────────────────────────

def test_deploy_if_ready_skips_below_threshold(db: Database) -> None:
    registry = MagicMock()
    historian = MagicMock()
    predictor = MagicMock()

    deployed, version = _deploy_if_ready(
        scope="futures",
        historian=historian,
        predictor=predictor,
        historian_acc=0.49,    # below MIN_ACCURACY_TO_DEPLOY
        predictor_acc=0.55,
        run_id="r1",
        registry=registry,
        db=db,
    )

    assert deployed is False
    assert version == "v0"
    registry.save.assert_not_called()


def test_deploy_if_ready_saves_both_models(db: Database) -> None:
    registry = MagicMock()
    registry.next_version.return_value = 3
    historian = MagicMock()
    historian.get_model_object.return_value = object()
    predictor = MagicMock()
    predictor.get_model_object.return_value = object()

    deployed, version = _deploy_if_ready(
        scope="futures",
        historian=historian,
        predictor=predictor,
        historian_acc=0.65,
        predictor_acc=0.61,
        run_id="r2",
        registry=registry,
        db=db,
    )

    assert deployed is True
    assert version == "v3"
    assert registry.save.call_count == 2
    save_calls = [c.kwargs["name"] for c in registry.save.call_args_list]
    assert "historian" in save_calls
    assert "predictor" in save_calls
