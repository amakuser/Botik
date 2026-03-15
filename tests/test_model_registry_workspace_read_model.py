from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.botik.gui.app import (
    build_model_registry_comparison,
    load_model_registry_workspace_read_model,
    promote_model_registry_model,
    write_active_model_pointer,
)
from src.botik.storage.sqlite_store import get_connection, upsert_model_registry


def _seed_model_registry(db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        upsert_model_registry(
            conn,
            model_id="spot-champion-v1",
            path_or_payload="data/models/spot-champion-v1.pkl",
            metrics_json=json.dumps(
                {
                    "instrument": "spot",
                    "policy": "hybrid",
                    "source_mode": "executed",
                    "status": "candidate",
                    "quality_score": 0.81,
                }
            ),
            created_at_utc="2026-03-14T09:00:00Z",
            is_active=True,
        )
        upsert_model_registry(
            conn,
            model_id="spot-challenger-v2",
            path_or_payload="data/models/spot-challenger-v2.pkl",
            metrics_json=json.dumps(
                {
                    "instrument": "spot",
                    "policy": "model",
                    "source_mode": "paper",
                    "status": "candidate",
                    "quality_score": 0.92,
                }
            ),
            created_at_utc="2026-03-14T10:00:00Z",
            is_active=False,
        )
        upsert_model_registry(
            conn,
            model_id="futures-paper-v3",
            path_or_payload="data/models/futures-paper-v3.pkl",
            metrics_json=json.dumps(
                {
                    "instrument": "futures",
                    "policy": "hard",
                    "source_mode": "paper",
                    "status": "candidate",
                    "quality_score": 0.66,
                }
            ),
            created_at_utc="2026-03-14T11:00:00Z",
            is_active=True,
        )
        conn.commit()
    finally:
        conn.close()


def test_model_registry_workspace_read_model_builds_roles_and_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "model_registry_workspace.db"
    _seed_model_registry(db_path)

    read_model = load_model_registry_workspace_read_model(
        db_path,
        release_manifest={
            "active_spot_model_version": "spot-champion-v1",
            "active_futures_model_version": "futures-paper-v3",
        },
    )

    assert read_model["total_models"] == 3
    assert read_model["spot_models"] == 2
    assert read_model["futures_models"] == 1
    assert "champion_spot=spot-champion-v1" in read_model["summary_line"]
    assert "champion_futures=futures-paper-v3" in read_model["summary_line"]
    assert "spot=review:spot-challenger-v2" in read_model["status_line"]
    assert "futures=hold:futures-paper-v3" in read_model["status_line"]
    rows = list(read_model["rows"])
    assert any(row[0] == "spot-champion-v1" and row[4] == "champion:spot" for row in rows)
    assert any(row[0] == "futures-paper-v3" and row[4] == "champion:futures" for row in rows)
    assert all("Start Trading" not in action for action in list(read_model["actions"]))


def test_write_active_model_pointer_updates_only_selected_instrument(tmp_path: Path) -> None:
    pointer_path = tmp_path / "active_models.yaml"
    pointer_path.write_text(
        "\n".join(
            [
                "manifest_version: 1",
                "product: botik_dashboard",
                "active_spot_model: spot-old",
                "active_futures_model: futures-old",
                "spot_checkpoint_path: \"\"",
                "futures_checkpoint_path: \"\"",
            ]
        ),
        encoding="utf-8",
    )

    ok, message = write_active_model_pointer("spot-new", "spot", path=pointer_path)
    assert ok is True
    assert "active_spot_model=spot-new" in message
    content = pointer_path.read_text(encoding="utf-8")
    assert "active_spot_model: spot-new" in content
    assert "active_futures_model: futures-old" in content


def test_promote_model_registry_model_clears_only_same_instrument_slot(tmp_path: Path) -> None:
    db_path = tmp_path / "model_registry_promote.db"
    _seed_model_registry(db_path)

    ok, message = promote_model_registry_model(db_path, "spot-challenger-v2", "spot")
    assert ok is True
    assert "spot" in message

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT model_id, is_active FROM model_registry ORDER BY model_id ASC"
        ).fetchall()
    finally:
        conn.close()

    states = {str(model_id): int(is_active or 0) for model_id, is_active in rows}
    assert states["spot-champion-v1"] == 0
    assert states["spot-challenger-v2"] == 1
    assert states["futures-paper-v3"] == 1


def test_model_registry_workspace_read_model_safe_fallback_when_db_missing(tmp_path: Path) -> None:
    read_model = load_model_registry_workspace_read_model(
        tmp_path / "absent.db",
        release_manifest={
            "active_spot_model_version": "spot-x",
            "active_futures_model_version": "futures-y",
        },
    )
    assert read_model["total_models"] == 0
    assert "champion_spot=spot-x" in read_model["summary_line"]
    assert list(read_model["rows"]) == []


def test_build_model_registry_comparison_prefers_stronger_candidate() -> None:
    comparison = build_model_registry_comparison(
        {
            "model_id": "challenger-a",
            "status": "candidate",
            "outcomes": 18,
            "win_rate": 0.64,
            "net_pnl": 2.75,
            "edge": 0.91,
        },
        {
            "model_id": "champion-b",
            "status": "candidate",
            "outcomes": 12,
            "win_rate": 0.55,
            "net_pnl": 1.10,
            "edge": 0.42,
        },
    )
    assert comparison["verdict"] == "prefer:challenger-a"
    assert "prefer challenger-a" in comparison["summary"]
    assert "net_pnl favors challenger-a" in comparison["reason_line"]
