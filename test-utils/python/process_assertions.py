from __future__ import annotations

import psutil


def pid_exists(pid: int) -> bool:
    return psutil.pid_exists(pid)
