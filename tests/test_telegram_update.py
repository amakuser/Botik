from __future__ import annotations

from pathlib import Path

from src.botik.control import telegram_bot
from src.botik.state.state import TradingState


def test_version_file_roundtrip(tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    telegram_bot._write_version_file(vf, "abc123")
    assert telegram_bot._read_version_file(vf) == "abc123"


def test_perform_update_up_to_date(monkeypatch, tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    vf.write_text("samehash\n", encoding="utf-8")

    def fake_run_git(args: list[str], _repo_root: Path) -> tuple[int, str]:
        if args[:4] == ["ls-remote", "--heads", "origin", "master"]:
            return 0, "samehash\trefs/heads/master"
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "samehash\n"
        return 0, ""

    monkeypatch.setattr(telegram_bot, "_run_git", fake_run_git)
    status, payload = telegram_bot.perform_update(tmp_path, vf)
    assert status == "up_to_date"
    assert payload == "samehash"


def test_perform_update_pull_success(monkeypatch, tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    vf.write_text("oldhash\n", encoding="utf-8")
    calls: list[list[str]] = []
    pulled = {"value": False}

    def fake_run_git(args: list[str], _repo_root: Path) -> tuple[int, str]:
        calls.append(args)
        if args[:4] == ["ls-remote", "--heads", "origin", "master"]:
            return 0, "newhash\trefs/heads/master"
        if args[:2] == ["pull", "--ff-only"]:
            pulled["value"] = True
            return 0, "ok"
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, ("newhash\n" if pulled["value"] else "oldhash\n")
        return 0, ""

    monkeypatch.setattr(telegram_bot, "_run_git", fake_run_git)
    status, payload = telegram_bot.perform_update(tmp_path, vf)
    assert status == "updated"
    assert payload == "newhash"
    assert telegram_bot._read_version_file(vf) == "newhash"
    assert ["pull", "--ff-only"] in calls


def test_perform_update_blocks_dirty_tree(monkeypatch, tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    vf.write_text("oldhash\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_git(args: list[str], _repo_root: Path) -> tuple[int, str]:
        calls.append(args)
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "oldhash\n"
        if args[:2] == ["status", "--porcelain"]:
            return 0, " M src/botik/main.py"
        return 0, ""

    monkeypatch.setattr(telegram_bot, "_run_git", fake_run_git)
    status, payload = telegram_bot.perform_update(tmp_path, vf)
    assert status == "dirty_tree"
    assert "src/botik/main.py" in payload
    assert ["pull", "--ff-only"] not in calls


def test_perform_update_ignores_local_version_file_change(monkeypatch, tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    vf.write_text("samehash\n", encoding="utf-8")

    def fake_run_git(args: list[str], _repo_root: Path) -> tuple[int, str]:
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "samehash\n"
        if args[:2] == ["status", "--porcelain"]:
            return 0, " M version.txt"
        if args[:4] == ["ls-remote", "--heads", "origin", "master"]:
            return 0, "samehash\trefs/heads/master"
        return 0, ""

    monkeypatch.setattr(telegram_bot, "_run_git", fake_run_git)
    status, payload = telegram_bot.perform_update(tmp_path, vf)
    assert status == "up_to_date"
    assert payload == "samehash"


def test_status_text_contains_version_and_update_flags(monkeypatch, tmp_path: Path) -> None:
    vf = tmp_path / "version.txt"
    vf.write_text("ver1234567890\n", encoding="utf-8")
    monkeypatch.setattr(telegram_bot, "VERSION_FILE", vf)

    state = TradingState()
    state.set_current_version("ver1234567890")
    state.set_update_in_progress(True, "checking")
    txt = telegram_bot._runtime_status_text(state)
    assert "Версия:" in txt
    assert "Update: IN_PROGRESS" in txt
