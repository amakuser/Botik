from __future__ import annotations

from src.botik.gui.app import build_worker_launch_command


def test_build_worker_launch_command_source_trading() -> None:
    cmd, supported, reason = build_worker_launch_command(
        process_kind="trading",
        launcher_mode="source",
        python_path="C:/Python/python.exe",
        config_path="config.runtime.yaml",
    )
    assert supported is True
    assert reason == "source"
    assert cmd == [
        "C:/Python/python.exe",
        "-m",
        "src.botik.main",
        "--config",
        "config.runtime.yaml",
    ]


def test_build_worker_launch_command_source_ml() -> None:
    cmd, supported, reason = build_worker_launch_command(
        process_kind="ml",
        launcher_mode="source",
        python_path="C:/Python/python.exe",
        config_path="config.yaml",
        ml_mode="online",
    )
    assert supported is True
    assert reason == "source"
    assert cmd == [
        "C:/Python/python.exe",
        "-m",
        "ml_service.run_loop",
        "--config",
        "config.yaml",
        "--mode",
        "online",
    ]


def test_build_worker_launch_command_packaged_trading() -> None:
    cmd, supported, reason = build_worker_launch_command(
        process_kind="trading",
        launcher_mode="packaged",
        python_path="ignored",
        config_path="runtime.spot.yaml",
        packaged_executable="C:/Botik/botik.exe",
    )
    assert supported is True
    assert reason == "packaged"
    assert cmd == [
        "C:/Botik/botik.exe",
        "--nogui",
        "--role",
        "trading",
        "--config",
        "runtime.spot.yaml",
    ]
    assert "-m" not in cmd


def test_build_worker_launch_command_packaged_ml() -> None:
    cmd, supported, reason = build_worker_launch_command(
        process_kind="ml",
        launcher_mode="packaged",
        python_path="ignored",
        config_path="config.yaml",
        packaged_executable="C:/Botik/botik.exe",
        ml_mode="train",
    )
    assert supported is True
    assert reason == "packaged"
    assert cmd == [
        "C:/Botik/botik.exe",
        "--nogui",
        "--role",
        "ml",
        "--config",
        "config.yaml",
        "--ml-mode",
        "train",
    ]
    assert "-m" not in cmd
