from __future__ import annotations

from src.botik.gui.app import dashboard_workspace_labels


def test_dashboard_workspace_labels_match_shell_layout() -> None:
    assert dashboard_workspace_labels() == [
        "Главная",
        "Спот",
        "Фьючерсы",
        "Модели",
        "Telegram",
        "Логи",
        "Состояние",
        "Настройки",
    ]
