from dataclasses import dataclass, field
from datetime import datetime

from botik_app_service.contracts.runtime_status import RuntimeId


@dataclass(frozen=True)
class RuntimeActivity:
    last_heartbeat_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


@dataclass(frozen=True)
class RuntimeObservation:
    runtime_id: RuntimeId
    label: str
    pids: list[int] = field(default_factory=list)
    activity: RuntimeActivity = field(default_factory=RuntimeActivity)
