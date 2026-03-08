"""
Windows packaged entrypoint.

Default mode: GUI desktop.
Optional: --nogui to run trading runtime without desktop window.
"""
from __future__ import annotations

import argparse
import os
import sys


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

    # Hint for runtime diagnostics.
    os.environ.setdefault("BOTIK_LAUNCH_MODE", "nogui" if args.nogui else "gui")
    if args.nogui:
        _run_nogui(args.config)
        return
    _run_gui()


if __name__ == "__main__":
    main()

