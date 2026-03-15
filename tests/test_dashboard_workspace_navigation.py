from __future__ import annotations

from src.botik.gui.app import BotikGui


def test_open_model_registry_workspace_routes_to_model_registry_tab() -> None:
    gui = BotikGui.__new__(BotikGui)
    model_registry_tab = object()
    opened: list[object] = []

    gui.model_registry_tab = model_registry_tab
    gui._open_workspace = opened.append  # type: ignore[method-assign]

    gui.open_model_registry_workspace()

    assert opened == [model_registry_tab]
