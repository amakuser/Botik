from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class DbProbeResult:
    """Raw outcome of a single SQLite probe."""
    success: bool
    latency_ms: float | None
    error: str | None
    probed_at: datetime
    db_path: str
