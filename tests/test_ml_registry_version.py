"""
Тесты для ModelRegistry._get_latest_version — диск-первая логика.
Задача #5: ML модели + исправление LIKE-бага в registry.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.botik.ml.registry import ModelRegistry, MODELS_DIR


def _make_registry() -> ModelRegistry:
    return ModelRegistry()


def test_get_latest_version_returns_none_when_no_files_and_no_db(tmp_path: Path) -> None:
    registry = _make_registry()
    # Патчим MODELS_DIR на пустую временную директорию
    with patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_db.connect.return_value = mock_conn
        with patch("src.botik.storage.db.get_db", return_value=mock_db):
            result = registry._get_latest_version("futures", "historian")
    assert result is None


def test_get_latest_version_reads_version_from_disk(tmp_path: Path) -> None:
    registry = _make_registry()
    # Создаём файлы модели
    (tmp_path / "futures_historian_v1.joblib").write_bytes(b"fake")
    (tmp_path / "futures_historian_v3.joblib").write_bytes(b"fake")
    (tmp_path / "futures_historian_v2.joblib").write_bytes(b"fake")

    with patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        result = registry._get_latest_version("futures", "historian")
    assert result == 3


def test_get_latest_version_disk_takes_priority_over_db(tmp_path: Path) -> None:
    registry = _make_registry()
    (tmp_path / "spot_predictor_v5.joblib").write_bytes(b"fake")

    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    # БД говорит v2, но на диске v5 — диск должен победить
    mock_conn.execute.return_value.fetchone.return_value = ("v2",)
    mock_db.connect.return_value = mock_conn

    with (
        patch("src.botik.ml.registry.MODELS_DIR", tmp_path),
        patch("src.botik.storage.db.get_db", return_value=mock_db),
    ):
        result = registry._get_latest_version("spot", "predictor")
    assert result == 5


def test_next_version_returns_one_when_no_models(tmp_path: Path) -> None:
    registry = _make_registry()
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchone.return_value = None
    mock_db.connect.return_value = mock_conn
    with (
        patch("src.botik.ml.registry.MODELS_DIR", tmp_path),
        patch("src.botik.storage.db.get_db", return_value=mock_db),
    ):
        v = registry.next_version("futures", "historian")
    assert v == 1


def test_next_version_increments_latest(tmp_path: Path) -> None:
    registry = _make_registry()
    (tmp_path / "futures_predictor_v4.joblib").write_bytes(b"fake")
    with patch("src.botik.ml.registry.MODELS_DIR", tmp_path):
        v = registry.next_version("futures", "predictor")
    assert v == 5
