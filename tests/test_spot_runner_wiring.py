"""
Тесты для SpotRunner — инициализация и ML wiring.
Задачи #6 (спот demo account) и #7 (спот ML модели).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _make_spot_runner() -> object:
    """Создаём SpotRunner без реального WS/БД."""
    # Мокаем bootstrap_db и get_db, чтобы не подключаться к реальной БД
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_db.connect.return_value = mock_conn

    with (
        patch("src.botik.storage.schema.bootstrap_db", return_value=mock_db),
        patch("src.botik.storage.db.get_db", return_value=mock_db),
    ):
        from src.botik.runners.spot_runner import SpotRunner
        runner = SpotRunner()
    return runner


def test_spot_runner_creates_engine_and_sizer() -> None:
    from src.botik.execution.spot_paper import SpotPaperEngine
    from src.botik.position.sizer import PositionSizer

    runner = _make_spot_runner()
    assert isinstance(runner.engine, SpotPaperEngine)
    assert isinstance(runner.sizer, PositionSizer)


def test_spot_runner_sets_model_scope_spot() -> None:
    runner = _make_spot_runner()
    # Trainer должен быть инициализирован с model_scope="spot"
    assert runner._trainer.model_scope == "spot"  # type: ignore[attr-defined]


def test_spot_runner_wires_predict_fn_attribute() -> None:
    runner = _make_spot_runner()
    # _predict_fn должен быть либо callable, либо None
    fn = runner._predict_fn  # type: ignore[attr-defined]
    assert fn is None or callable(fn)


def test_spot_runner_has_poller() -> None:
    from src.botik.marketdata.rest_private_poller import RestPrivatePoller
    runner = _make_spot_runner()
    assert isinstance(runner._poller, RestPrivatePoller)


def test_spot_runner_poller_category_is_spot() -> None:
    runner = _make_spot_runner()
    assert runner._poller.category == "spot"  # type: ignore[attr-defined]


def test_spot_runner_price_buf_initialized_for_all_symbols() -> None:
    from src.botik.runners.spot_runner import SYMBOLS
    runner = _make_spot_runner()
    for symbol in SYMBOLS:
        assert symbol in runner._price_buf  # type: ignore[attr-defined]


def test_spot_runner_starts_running() -> None:
    runner = _make_spot_runner()
    assert runner._running is True  # type: ignore[attr-defined]
