from __future__ import annotations

import sys

from src.botik import windows_entry


def test_windows_entry_defaults_to_gui(monkeypatch) -> None:
    called = {"gui": False, "nogui": False}

    def _fake_gui() -> None:
        called["gui"] = True

    def _fake_nogui(config: str | None) -> None:
        called["nogui"] = True

    monkeypatch.setattr(windows_entry, "_run_gui", _fake_gui)
    monkeypatch.setattr(windows_entry, "_run_nogui", _fake_nogui)
    monkeypatch.setattr(windows_entry, "_log", lambda *_: None)
    monkeypatch.setattr(windows_entry, "_show_error_box", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["botik.exe"])

    windows_entry.main()

    assert called["gui"] is True
    assert called["nogui"] is False


def test_windows_entry_nogui_mode(monkeypatch) -> None:
    called = {"gui": False, "nogui": False, "config": None}

    def _fake_gui() -> None:
        called["gui"] = True

    def _fake_nogui(config: str | None) -> None:
        called["nogui"] = True
        called["config"] = config

    monkeypatch.setattr(windows_entry, "_run_gui", _fake_gui)
    monkeypatch.setattr(windows_entry, "_run_nogui", _fake_nogui)
    monkeypatch.setattr(windows_entry, "_log", lambda *_: None)
    monkeypatch.setattr(windows_entry, "_show_error_box", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["botik.exe", "--nogui", "--config", "config.yaml"])

    windows_entry.main()

    assert called["gui"] is False
    assert called["nogui"] is True
    assert called["config"] == "config.yaml"
