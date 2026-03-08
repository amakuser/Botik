"""
Windows packaged entrypoint.

Default mode: GUI desktop.
Optional: --nogui to run trading runtime without desktop window.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from src.botik.utils.runtime import runtime_root


ROOT_DIR = runtime_root(__file__, levels_up=2)
LOG_DIR = ROOT_DIR / "logs" / "script_logs"
LOG_FILE = LOG_DIR / "windows_entry.log"


def _log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} {message}\n")
    except OSError:
        pass


def _show_error_box(text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, "Botik startup error", 0x10)
    except Exception:
        pass


def _run_gui() -> None:
    from src.botik.gui.app import main as gui_main

    gui_main()


def _run_nogui(config: str | None) -> None:
    from src.botik.main import main as trading_main

    argv = [sys.argv[0]]
    if config:
        argv.extend(["--config", config])
    old_argv = sys.argv[:]
    try:
        sys.argv = argv
        trading_main()
    finally:
        sys.argv = old_argv


def main() -> None:
    parser = argparse.ArgumentParser(description="Botik Windows launcher")
    parser.add_argument("--nogui", action="store_true", help="Run trading runtime without desktop UI.")
    parser.add_argument("--config", type=str, default=None, help="Optional config path for --nogui mode.")
    args = parser.parse_args()

    launch_mode = "nogui" if args.nogui else "gui"
    _log(f"windows_entry start mode={launch_mode} cwd={Path.cwd()}")
    # Hint for runtime diagnostics.
    os.environ.setdefault("BOTIK_LAUNCH_MODE", launch_mode)
    try:
        if args.nogui:
            _run_nogui(args.config)
            return
        _run_gui()
    except Exception:
        _log("windows_entry fatal error")
        _log(traceback.format_exc())
        _show_error_box(f"Botik failed to start.\nSee log:\n{LOG_FILE}")
        raise


if __name__ == "__main__":
    main()
