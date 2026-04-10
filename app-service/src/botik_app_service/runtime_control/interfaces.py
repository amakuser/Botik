from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from botik_app_service.contracts.runtime_status import RuntimeId


RuntimeControlMode = Literal["auto", "fixture", "compatibility"]


@dataclass(frozen=True)
class RuntimeCommandSpec:
    command: list[str]
    cwd: str
    env: dict[str, str]
    control_file: Path
    mode: Literal["fixture", "legacy"]


@dataclass(frozen=True)
class RuntimeHeartbeat:
    runtime_id: RuntimeId
    timestamp: datetime


@dataclass(frozen=True)
class RuntimeFailure:
    runtime_id: RuntimeId
    message: str
    timestamp: datetime
