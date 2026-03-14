from __future__ import annotations

from src.botik.gui.app import dashboard_workspace_labels


def test_dashboard_workspace_labels_match_shell_layout() -> None:
    assert dashboard_workspace_labels() == [
        "Dashboard Home",
        "Spot Workspace",
        "Futures Workspace",
        "Model Registry Workspace",
        "Telegram Workspace",
        "Logs Workspace",
        "Ops Workspace",
        "Settings Workspace",
    ]
