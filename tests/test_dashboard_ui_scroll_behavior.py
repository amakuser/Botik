from __future__ import annotations

from types import SimpleNamespace

from src.botik.gui.app import (
    bind_dashboard_mousewheel,
    build_dashboard_mousewheel_handler,
    dashboard_mousewheel_units,
    format_dashboard_status_block,
)


class _ScrollableStub:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def yview_scroll(self, units: int, mode: str) -> None:
        self.calls.append((units, mode))


class _WidgetStub:
    def __init__(self) -> None:
        self.bindings: list[tuple[str, object, str | None]] = []

    def bind(self, sequence: str, handler: object, add: str | None = None) -> str:
        self.bindings.append((sequence, handler, add))
        return "ok"


def test_dashboard_mousewheel_units_supports_windows_and_x11_events() -> None:
    assert dashboard_mousewheel_units(SimpleNamespace(delta=120, num=0)) == -1
    assert dashboard_mousewheel_units(SimpleNamespace(delta=-240, num=0)) == 2
    assert dashboard_mousewheel_units(SimpleNamespace(delta=0, num=4)) == -1
    assert dashboard_mousewheel_units(SimpleNamespace(delta=0, num=5)) == 1
    assert dashboard_mousewheel_units(SimpleNamespace(delta=0, num=0)) == 0


def test_build_dashboard_mousewheel_handler_scrolls_and_returns_break() -> None:
    scrollable = _ScrollableStub()
    handler = build_dashboard_mousewheel_handler(scrollable.yview_scroll)

    result = handler(SimpleNamespace(delta=-120, num=0))

    assert result == "break"
    assert scrollable.calls == [(1, "units")]


def test_bind_dashboard_mousewheel_registers_expected_sequences() -> None:
    widget = _WidgetStub()
    scrollable = _ScrollableStub()

    bind_dashboard_mousewheel(widget, scrollable)

    sequences = [sequence for sequence, _, _ in widget.bindings]
    assert sequences == ["<MouseWheel>", "<Button-4>", "<Button-5>"]
    for _, _, add in widget.bindings:
        assert add == "+"


def test_format_dashboard_status_block_breaks_pipe_delimited_content_into_lines() -> None:
    panel = format_dashboard_status_block(
        "release=loaded | workspace_manifest=loaded | active_models_manifest=loaded",
        "workspace_pack=0.0.18 | spot_model=spot-v7",
    )

    assert "Релиз: loaded" in panel
    assert "Manifest рабочих пространств: loaded" in panel
    assert "Manifest активных моделей: loaded" in panel
    assert "Workspace pack: 0.0.18" in panel
    assert "Модель Spot: spot-v7" in panel
    assert "\n" in panel
