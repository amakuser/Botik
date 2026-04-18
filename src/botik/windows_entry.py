"""
Windows packaged entrypoint.

Default mode: Dashboard Shell desktop.
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


def _wait_for_service(url: str, timeout: float = 10.0) -> bool:
    import urllib.request
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)  # noqa: S310
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _run_gui() -> None:
    import asyncio
    import subprocess
    import threading
    import webbrowser

    # In dev (non-frozen) mode add app-service to sys.path
    if not getattr(sys, "frozen", False):
        _svc = ROOT_DIR / "app-service" / "src"
        if str(_svc) not in sys.path:
            sys.path.insert(0, str(_svc))

    import uvicorn
    from botik_app_service.main import create_app

    _log("Starting app-service in-process")
    botik_app = create_app()

    def _serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(botik_app, host="127.0.0.1", port=8765, log_level="warning")
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve())
        except Exception as exc:
            _log(f"app-service crashed: {exc}")
        finally:
            loop.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    # Wait until app-service is ready
    if not _wait_for_service("http://127.0.0.1:8765/health"):
        _log("app-service did not start in time")

    # Prefer Tauri desktop window; fall back to browser
    desktop_exe = ROOT_DIR / "botik_desktop.exe"
    if desktop_exe.exists():
        _log(f"Launching Tauri window: {desktop_exe}")
        proc = subprocess.Popen([str(desktop_exe)])
        proc.wait()
    else:
        _log("botik_desktop.exe not found — opening browser at http://127.0.0.1:8765")
        webbrowser.open("http://127.0.0.1:8765")
        t.join()


def _run_worker(worker_type: str, worker_args: list[str]) -> None:
    """Dispatch to background worker entry points (backfill / live / training).

    Called when the exe is launched with ``--worker <type>`` from ManagedProcess.
    """
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if worker_type == "backfill":
        from src.botik.data.backfill_entry import main
        sys.exit(main(worker_args))
    elif worker_type == "live":
        from src.botik.data.live_entry import main
        sys.exit(main(worker_args))
    elif worker_type == "training":
        from src.botik.data.training_worker import main
        sys.exit(main(worker_args))
    sys.exit(1)


def _run_nogui(config: str | None, *, role: str = "trading", ml_mode: str | None = None) -> None:
    role_norm = str(role or "trading").strip().lower() or "trading"
    argv = [sys.argv[0]]
    if config:
        argv.extend(["--config", config])
    old_argv = sys.argv[:]
    try:
        sys.argv = argv
        if role_norm == "ml":
            from ml_service.run_loop import main as ml_main

            mode = str(ml_mode or "").strip().lower()
            if mode in {"bootstrap", "train", "predict", "online"}:
                sys.argv.extend(["--mode", mode])
            ml_main()
            return
        from src.botik.main import main as trading_main

        trading_main()
    finally:
        sys.argv = old_argv


def main() -> None:
    parser = argparse.ArgumentParser(description="Botik Windows launcher")
    parser.add_argument("--nogui", action="store_true", help="Run trading runtime without desktop UI.")
    parser.add_argument(
        "--role",
        choices=["trading", "ml"],
        default="trading",
        help="Worker role for --nogui mode.",
    )
    parser.add_argument(
        "--ml-mode",
        choices=["bootstrap", "train", "predict", "online"],
        default=None,
        help="ML mode for --nogui --role ml.",
    )
    parser.add_argument("--config", type=str, default=None, help="Optional config path for --nogui mode.")
    parser.add_argument(
        "--worker",
        choices=["backfill", "live", "training"],
        default=None,
        help="Run a background worker subprocess (used internally by the dashboard).",
    )
    # Use parse_known_args so worker-specific flags (--scope, --category, etc.)
    # are passed through unchanged to the worker's own argparse.
    args, remaining = parser.parse_known_args()

    if args.worker:
        _run_worker(args.worker, remaining)
        return

    launch_mode = f"nogui:{args.role}" if args.nogui else "gui"
    _log(f"windows_entry start mode={launch_mode} cwd={Path.cwd()}")
    # Hint for runtime diagnostics.
    os.environ.setdefault("BOTIK_LAUNCH_MODE", launch_mode)
    try:
        if args.nogui:
            _run_nogui(args.config, role=args.role, ml_mode=args.ml_mode)
            return
        _run_gui()
    except Exception:
        _log("windows_entry fatal error")
        _log(traceback.format_exc())
        _show_error_box(f"Botik failed to start.\nSee log:\n{LOG_FILE}")
        raise


if __name__ == "__main__":
    main()
