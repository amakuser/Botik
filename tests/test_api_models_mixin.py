"""
Tests for ModelsMixin M5/M6 additions: get_model_cards(), get_model_logs(),
_get_data_readiness().

Verifies:
- get_model_cards() returns 6 cards (historian/predictor/outcome × futures/spot)
- each card has required fields: scope, name, state, tag_class, tag_text, etc.
- state logic: has_file + is_trained → "active"; has_file, not trained → "ready"
- state logic: no file + running run → "training"; no file + old run → "idle"
- state logic: no file, no runs → "missing"
- outcome model: no training runs, has_file → "active"; no file → "missing"
- get_model_logs() returns logs for valid scope (futures/spot)
- get_model_logs() returns empty list for invalid scope
- get_model_cards() includes training_states and data_ready keys
- _get_data_readiness(): False when no data; True when candle_count >= 100
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.botik.storage.db import Database
from src.botik.storage.migrations import run_migrations
from src.botik.gui.api_models_mixin import ModelsMixin


# ─────────────────────────────────────────────────────────────────────────────
#  Test double
# ─────────────────────────────────────────────────────────────────────────────

class _StubAPI(ModelsMixin):
    """Minimal test double satisfying ModelsMixin's DbMixin dependencies."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    # ── DbMixin stubs ──────────────────────────────────────────────────────

    def _db_connect(self, db_path: Path) -> sqlite3.Connection | None:
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=3, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        try:
            conn.execute(f"SELECT 1 FROM {table_name} WHERE 1=0").fetchall()
            return True
        except Exception:
            return False

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            cur = conn.execute(f"SELECT * FROM {table_name} WHERE 1=0")
            return {str(c[0]) for c in (cur.description or [])}
        except Exception:
            return set()

    @staticmethod
    def _first_existing_column(columns: set[str], *candidates: str) -> str | None:
        for c in candidates:
            if c in columns:
                return c
        return None

    @classmethod
    def _column_expr(cls, columns: set[str], candidates, alias: str, *, default_sql: str = "NULL") -> str:
        col = cls._first_existing_column(columns, *(candidates if not isinstance(candidates, str) else [candidates]))
        return f"{col} AS {alias}" if col else f"{default_sql} AS {alias}"

    @staticmethod
    def _normalize_model_scope(value: Any, fallback: Any = "") -> str:
        text = str(value or "").strip().lower()
        hint = str(fallback or "").strip().lower()
        joined = f"{text} {hint}".strip()
        if "future" in joined or "linear" in joined:
            return "futures"
        if "spot" in joined:
            return "spot"
        return text or (hint if hint else "unknown")

    @staticmethod
    def _model_ids_match(left: Any, right: Any) -> bool:
        a = str(left or "").strip().lower()
        b = str(right or "").strip().lower()
        if not a or not b or a in {"unknown", "none", "null"} or b in {"unknown", "none", "null"}:
            return False
        return a == b or a.endswith(b) or b.endswith(a)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value in (None, "") else float(value)
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return None if value in (None, "") else int(value)
        except Exception:
            return None

    # ── TradingMixin stubs (used by _build_models_payload + get_model_cards) ─

    @property
    def _ml_process(self):
        from unittest.mock import MagicMock
        m = MagicMock(); m.state = "stopped"; return m

    @property
    def _ml_futures_process(self):
        from unittest.mock import MagicMock
        m = MagicMock(); m.state = "stopped"; return m

    @property
    def _ml_spot_process(self):
        from unittest.mock import MagicMock
        m = MagicMock(); m.state = "stopped"; return m


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> tuple[Database, Path]:
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_path}")
    with db.connect() as conn:
        run_migrations(conn)
    return db, db_path


def _patch_models_mixin(db_path: Path):
    """Patch _load_yaml and _resolve_db_path in api_helpers to use test DB."""
    import src.botik.gui.api_helpers as h
    return (
        patch.object(h, "_load_yaml",       lambda: {}),
        patch.object(h, "_resolve_db_path", lambda _: db_path),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  get_model_cards tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_model_cards_returns_six_cards(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    data = json.loads(raw)
    assert "cards" in data
    assert len(data["cards"]) == 6


def test_get_model_cards_required_fields(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    required = {"scope", "name", "state", "tag_class", "tag_text", "has_file", "version", "description"}
    for card in cards:
        assert required <= set(card.keys()), f"missing fields in card {card.get('name')}"


def test_get_model_cards_covers_all_combinations(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    combos = {(c["scope"], c["name"]) for c in cards}
    expected = {
        ("futures", "historian"), ("futures", "predictor"), ("futures", "outcome"),
        ("spot", "historian"), ("spot", "predictor"), ("spot", "outcome"),
    }
    assert combos == expected


def test_get_model_cards_missing_when_no_file_no_runs(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    for card in cards:
        assert card["state"] == "missing", f"expected missing for {card['name']}@{card['scope']}"
        assert card["tag_class"] == "tag-risk"


def test_get_model_cards_active_when_file_and_trained(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    # Create a fake .joblib file for futures_historian
    (tmp_path / "futures_historian_v1.joblib").touch()
    # Insert a completed training run
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ml_training_runs (model_scope, model_version, mode, status, is_trained, started_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("futures", "v1", "online", "completed", 1, "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    historian_futures = next(c for c in cards if c["scope"] == "futures" and c["name"] == "historian")
    assert historian_futures["state"] == "active"
    assert historian_futures["tag_class"] == "tag-active"
    assert historian_futures["has_file"] is True


def test_get_model_cards_ready_when_file_not_trained(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    (tmp_path / "futures_predictor_v2.joblib").touch()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ml_training_runs (model_scope, model_version, mode, status, is_trained, started_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("futures", "v2", "online", "completed", 0, "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    pred = next(c for c in cards if c["scope"] == "futures" and c["name"] == "predictor")
    assert pred["state"] == "ready"


def test_get_model_cards_training_when_run_running(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ml_training_runs (model_scope, model_version, mode, status, is_trained, started_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("spot", "v1", "online", "running", 0, "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    # historian and predictor for spot should be "training" (no file, run is running)
    hist_spot = next(c for c in cards if c["scope"] == "spot" and c["name"] == "historian")
    assert hist_spot["state"] == "training"
    assert hist_spot["tag_class"] == "tag-loading"


def test_get_model_cards_idle_when_runs_but_no_file(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ml_training_runs (model_scope, model_version, mode, status, is_trained, started_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("spot", "v1", "online", "completed", 0, "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    hist_spot = next(c for c in cards if c["scope"] == "spot" and c["name"] == "historian")
    assert hist_spot["state"] == "idle"
    assert hist_spot["tag_text"] == "NO FILE"


def test_get_model_cards_outcome_active_when_file_present(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    (tmp_path / "futures_outcome_v1.joblib").touch()
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    outcome = next(c for c in cards if c["scope"] == "futures" and c["name"] == "outcome")
    assert outcome["state"] == "active"


def test_get_model_cards_outcome_missing_without_file(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        raw = api.get_model_cards()
    cards = json.loads(raw)["cards"]
    outcome = next(c for c in cards if c["scope"] == "futures" and c["name"] == "outcome")
    assert outcome["state"] == "missing"


# ─────────────────────────────────────────────────────────────────────────────
#  get_model_logs tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_model_logs_empty_when_no_logs(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2:
        raw = api.get_model_logs("futures")
    data = json.loads(raw)
    assert "logs" in data
    assert data["logs"] == []


def test_get_model_logs_invalid_scope_returns_empty(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2:
        raw = api.get_model_logs("invalid_scope")
    data = json.loads(raw)
    assert data["logs"] == []


def test_get_model_logs_returns_channel_logs(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
            ("ml_futures", "INFO", "epoch 1/10 loss=0.42", "2026-03-22 10:00:00"),
        )
        conn.execute(
            "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
            ("ml_spot", "INFO", "spot log entry", "2026-03-22 10:00:01"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2:
        raw_futures = api.get_model_logs("futures")
        raw_spot    = api.get_model_logs("spot")
    logs_futures = json.loads(raw_futures)["logs"]
    logs_spot    = json.loads(raw_spot)["logs"]
    assert len(logs_futures) == 1
    assert logs_futures[0]["msg"] == "epoch 1/10 loss=0.42"
    assert len(logs_spot) == 1
    assert logs_spot[0]["msg"] == "spot log entry"


def test_get_model_logs_does_not_mix_channels(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
                ("ml_futures", "INFO", f"futures msg {i}", f"2026-03-22 10:00:0{i}"),
            )
        for i in range(3):
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, created_at_utc) VALUES (?, ?, ?, ?)",
                ("ml_spot", "INFO", f"spot msg {i}", f"2026-03-22 11:00:0{i}"),
            )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2:
        logs = json.loads(api.get_model_logs("futures"))["logs"]
    assert len(logs) == 5
    assert all("futures" in entry["msg"] for entry in logs)


# ─────────────────────────────────────────────────────────────────────────────
#  M6: training_states + data_ready in get_model_cards()
# ─────────────────────────────────────────────────────────────────────────────

def test_get_model_cards_includes_training_states(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert "training_states" in data
    assert "futures" in data["training_states"]
    assert "spot" in data["training_states"]


def test_get_model_cards_includes_data_ready(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert "data_ready" in data
    assert "futures" in data["data_ready"]
    assert "spot" in data["data_ready"]


def test_data_ready_false_when_no_symbol_registry(tmp_path: Path) -> None:
    _, db_path = _make_db(tmp_path)
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert data["data_ready"]["futures"] is False
    assert data["data_ready"]["spot"] is False


def test_data_ready_true_when_futures_has_enough_candles(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO symbol_registry (symbol, category, interval, candle_count, added_at_utc, updated_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("BTCUSDT", "linear", "1", 500, "2026-03-22 10:00:00", "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert data["data_ready"]["futures"] is True
    assert data["data_ready"]["spot"] is False


def test_data_ready_true_when_spot_has_enough_candles(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO symbol_registry (symbol, category, interval, candle_count, added_at_utc, updated_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("ETHUSDT", "spot", "1", 200, "2026-03-22 10:00:00", "2026-03-22 10:00:00"),
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert data["data_ready"]["spot"] is True
    assert data["data_ready"]["futures"] is False


def test_data_ready_false_when_candles_below_threshold(tmp_path: Path) -> None:
    db, db_path = _make_db(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO symbol_registry (symbol, category, interval, candle_count, added_at_utc, updated_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("BTCUSDT", "linear", "1", 50, "2026-03-22 10:00:00", "2026-03-22 10:00:00"),  # below 100
        )
    api = _StubAPI(db_path)
    p1, p2 = _patch_models_mixin(db_path)
    with p1, p2, patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        data = json.loads(api.get_model_cards())
    assert data["data_ready"]["futures"] is False
