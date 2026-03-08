from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

LOG_DIR = ROOT_DIR / "logs" / "script_logs"
LOG_FILE = LOG_DIR / "gui_bootstrap.log"


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


if __name__ == "__main__":
    _log("app.pyw startup")
    try:
        from src.botik.gui.app import main

        main()
        _log("app.pyw shutdown: ok")
    except Exception:
        tb = traceback.format_exc()
        _log("app.pyw startup failed")
        _log(tb)
        _show_error_box(f"Botik failed to start.\nSee log:\n{LOG_FILE}")
        raise
