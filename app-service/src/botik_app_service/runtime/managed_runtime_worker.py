from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def _wait_for_stop(control_file: Path, *, poll_seconds: float = 0.25) -> None:
    while not control_file.exists():
        await asyncio.sleep(poll_seconds)


async def _run_fixture(runtime_id: str, control_file: Path, heartbeat_interval: float) -> None:
    _emit({"type": "log", "level": "INFO", "runtime_id": runtime_id, "timestamp": _timestamp(), "message": f"{runtime_id} fixture runtime started."})
    while not control_file.exists():
        _emit({"type": "heartbeat", "runtime_id": runtime_id, "timestamp": _timestamp()})
        await asyncio.sleep(heartbeat_interval)
    _emit({"type": "log", "level": "INFO", "runtime_id": runtime_id, "timestamp": _timestamp(), "message": f"{runtime_id} fixture runtime stopping."})


def _load_legacy_runner(runtime_id: str):
    if runtime_id == "spot":
        from src.botik.runners.spot_runner import SpotRunner, bootstrap_db

        bootstrap_db()
        return SpotRunner()

    if runtime_id == "futures":
        from src.botik.runners.futures_runner import FuturesRunner, bootstrap_db

        bootstrap_db()
        return FuturesRunner()

    raise ValueError(f"Unsupported runtime: {runtime_id}")


async def _run_legacy(runtime_id: str, control_file: Path, heartbeat_interval: float) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    runner = _load_legacy_runner(runtime_id)
    stop_event = asyncio.Event()

    def request_stop() -> None:
        runner.stop()
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except (NotImplementedError, OSError):
            pass

    _emit({"type": "log", "level": "INFO", "runtime_id": runtime_id, "timestamp": _timestamp(), "message": f"{runtime_id} legacy runtime wrapper started."})
    run_task = asyncio.create_task(runner.run())
    stop_task = asyncio.create_task(_wait_for_stop(control_file))

    try:
        while not run_task.done():
            if stop_task.done() and not stop_event.is_set():
                request_stop()
                _emit(
                    {
                        "type": "log",
                        "level": "INFO",
                        "runtime_id": runtime_id,
                        "timestamp": _timestamp(),
                        "message": f"{runtime_id} runtime stop requested.",
                    }
                )
            _emit({"type": "heartbeat", "runtime_id": runtime_id, "timestamp": _timestamp()})
            await asyncio.sleep(heartbeat_interval)

        await run_task
    finally:
        if stop_event.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(run_task, timeout=8.0)
        if not run_task.done():
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task
        stop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stop_task
        _emit({"type": "log", "level": "INFO", "runtime_id": runtime_id, "timestamp": _timestamp(), "message": f"{runtime_id} legacy runtime wrapper stopped."})


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-id", required=True, choices=["spot", "futures"])
    parser.add_argument("--mode", required=True, choices=["fixture", "legacy"])
    parser.add_argument("--control-file", required=True)
    parser.add_argument("--heartbeat-interval", type=float, default=1.0)
    args = parser.parse_args()

    control_file = Path(args.control_file)
    control_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.mode == "fixture":
            await _run_fixture(args.runtime_id, control_file, args.heartbeat_interval)
        else:
            await _run_legacy(args.runtime_id, control_file, args.heartbeat_interval)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
