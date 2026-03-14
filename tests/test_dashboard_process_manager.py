from __future__ import annotations

import subprocess

from src.botik.gui import app


def test_dashboard_subprocess_popen_kwargs_windows(monkeypatch) -> None:
    class _StartupInfo:
        def __init__(self) -> None:
            self.dwFlags = 0
            self.wShowWindow = 1

    monkeypatch.setattr(app.os, "name", "nt", raising=False)
    monkeypatch.setattr(app.subprocess, "STARTUPINFO", _StartupInfo, raising=False)
    monkeypatch.setattr(app.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(app.subprocess, "STARTF_USESHOWWINDOW", 0x00000001, raising=False)
    monkeypatch.setattr(app.subprocess, "SW_HIDE", 0, raising=False)

    kwargs = app.dashboard_subprocess_popen_kwargs()

    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags & 0x00000001
    assert kwargs["startupinfo"].wShowWindow == 0


def test_managed_process_start_uses_hidden_popen_kwargs(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class _DummyProc:
        def __init__(self) -> None:
            self.stdout = []

        def poll(self) -> None:
            return None

    class _DummyThread:
        def __init__(self, target=None, daemon=None) -> None:
            self.target = target
            self.daemon = daemon

        def start(self) -> None:
            return

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _DummyProc()

    monkeypatch.setattr(app, "dashboard_subprocess_popen_kwargs", lambda: {"creationflags": 123, "stdin": "DEVNULL"})
    monkeypatch.setattr(app.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(app.threading, "Thread", _DummyThread)

    proc = app.ManagedProcess("worker", lambda *_: None)
    started = proc.start(["botik.exe", "--nogui"], tmp_path)

    assert started is True
    assert captured["cmd"] == ["botik.exe", "--nogui"]
    assert captured["kwargs"]["creationflags"] == 123
    assert captured["kwargs"]["stdin"] == "DEVNULL"


def test_start_trading_dispatches_async_service_action(monkeypatch) -> None:
    gui = app.BotikGui.__new__(app.BotikGui)
    called: dict[str, object] = {}
    logs: list[str] = []

    monkeypatch.setattr(gui, "_load_execution_mode", lambda: "paper")
    monkeypatch.setattr(gui, "_enqueue_log", logs.append)

    def _fake_async(action_key, fn, *, queued_message):
        called["action_key"] = action_key
        called["queued_message"] = queued_message
        called["result"] = fn()

    monkeypatch.setattr(gui, "_run_dashboard_service_action_async", _fake_async)
    monkeypatch.setattr(gui, "_start_trading_impl", lambda interactive, start_ml=True: f"interactive={interactive}|ml={start_ml}")

    gui.start_trading()

    assert called["action_key"] == "start_trading"
    assert called["queued_message"] == "queued start_trading"
    assert called["result"] == "interactive=False|ml=True"
    assert logs == []


def test_start_ml_dispatches_async_service_action(monkeypatch) -> None:
    gui = app.BotikGui.__new__(app.BotikGui)
    called: dict[str, object] = {}

    def _fake_async(action_key, fn, *, queued_message):
        called["action_key"] = action_key
        called["queued_message"] = queued_message
        called["result"] = fn()

    monkeypatch.setattr(gui, "_run_dashboard_service_action_async", _fake_async)
    monkeypatch.setattr(gui, "_start_ml_impl", lambda: "ML process started.")

    gui.start_ml()

    assert called["action_key"] == "start_ml"
    assert called["queued_message"] == "queued start_ml"
    assert called["result"] == "ML process started."
