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


def _run_gui() -> None:
    import subprocess
    import time
    import webbrowser

    _log("Starting app-service + opening browser")
    root = ROOT_DIR

    app_service_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "botik_app_service.main:app",
         "--host", "127.0.0.1", "--port", "8765", "--no-access-log"],
        cwd=str(root / "app-service" / "src"),
    )

    # Try Tauri desktop exe first
    tauri_exe = root / "apps" / "desktop" / "src-tauri" / "target" / "release" / "botik_desktop.exe"
    if tauri_exe.exists():
        tauri_proc = subprocess.Popen([str(tauri_exe)])
        tauri_proc.wait()
    else:
        # Fallback: open browser after app-service starts
        _log("Tauri exe not found — opening browser at http://127.0.0.1:8765")
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8765")
        try:
            app_service_proc.wait()
        except KeyboardInterrupt:
            pass

    app_service_proc.terminate()


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
