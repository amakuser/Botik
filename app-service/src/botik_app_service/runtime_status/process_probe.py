from __future__ import annotations

from collections.abc import Iterable

import psutil

from botik_app_service.contracts.runtime_status import RuntimeId


RUNTIME_COMMAND_PATTERNS: dict[RuntimeId, tuple[str, ...]] = {
    "spot": ("src.botik.runners.spot_runner", "botik.runners.spot_runner"),
    "futures": ("src.botik.runners.futures_runner", "botik.runners.futures_runner"),
}


class RuntimeProcessProbe:
    def scan(self) -> dict[RuntimeId, list[int]]:
        discovered: dict[RuntimeId, list[int]] = {"spot": [], "futures": []}
        for process in psutil.process_iter(attrs=["pid", "cmdline"]):
            try:
                pid = int(process.info["pid"])
                cmdline = self._join_cmdline(process.info.get("cmdline"))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
                continue

            for runtime_id, patterns in RUNTIME_COMMAND_PATTERNS.items():
                if any(pattern in cmdline for pattern in patterns):
                    discovered[runtime_id].append(pid)
        return discovered

    @staticmethod
    def _join_cmdline(cmdline: object) -> str:
        if isinstance(cmdline, str):
            return cmdline
        if isinstance(cmdline, Iterable):
            return " ".join(str(part) for part in cmdline)
        return ""
