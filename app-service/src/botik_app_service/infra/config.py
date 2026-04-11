import os
from pathlib import Path

from pydantic import BaseModel, Field


def _read_version() -> str:
    repo_root = Path(__file__).resolve().parents[4]
    version_file = repo_root / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0-dev"


class Settings(BaseModel):
    service_name: str = "botik-app-service"
    app_name: str = "Botik Foundation"
    version: str = Field(default_factory=_read_version)
    host: str = "127.0.0.1"
    port: int = 8765
    session_token: str = "botik-dev-token"
    frontend_url: str = "http://127.0.0.1:4173"
    desktop_mode: bool = False
    sse_heartbeat_interval_seconds: float = 5.0
    event_buffer_size: int = 32
    log_channel_buffer_size: int = 200
    log_snapshot_limit: int = 100
    artifacts_dir: Path | None = None
    legacy_runtime_log_path: Path | None = None
    runtime_status_heartbeat_stale_seconds: float = 120.0
    runtime_status_fixture_path: Path | None = None
    runtime_control_mode: str = "auto"
    runtime_control_heartbeat_interval_seconds: float = 1.0
    runtime_control_stop_timeout_seconds: float = 8.0
    spot_read_fixture_db_path: Path | None = None
    spot_read_account_type: str = "UNIFIED"
    futures_read_fixture_db_path: Path | None = None
    futures_read_account_type: str = "UNIFIED"
    telegram_ops_fixture_path: Path | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            service_name=os.getenv("BOTIK_APP_SERVICE_NAME", "botik-app-service"),
            app_name=os.getenv("BOTIK_APP_NAME", "Botik Foundation"),
            version=os.getenv("BOTIK_APP_VERSION", _read_version()),
            host=os.getenv("BOTIK_APP_SERVICE_HOST", "127.0.0.1"),
            port=int(os.getenv("BOTIK_APP_SERVICE_PORT", "8765")),
            session_token=os.getenv("BOTIK_SESSION_TOKEN", "botik-dev-token"),
            frontend_url=os.getenv("BOTIK_FRONTEND_URL", "http://127.0.0.1:4173"),
            desktop_mode=os.getenv("BOTIK_DESKTOP_MODE", "false").lower() == "true",
            sse_heartbeat_interval_seconds=float(os.getenv("BOTIK_SSE_HEARTBEAT_SECONDS", "5.0")),
            event_buffer_size=int(os.getenv("BOTIK_EVENT_BUFFER_SIZE", "32")),
            log_channel_buffer_size=int(os.getenv("BOTIK_LOG_CHANNEL_BUFFER_SIZE", "200")),
            log_snapshot_limit=int(os.getenv("BOTIK_LOG_SNAPSHOT_LIMIT", "100")),
            artifacts_dir=Path(os.getenv("BOTIK_ARTIFACTS_DIR")) if os.getenv("BOTIK_ARTIFACTS_DIR") else None,
            legacy_runtime_log_path=Path(os.getenv("BOTIK_LEGACY_RUNTIME_LOG_PATH"))
            if os.getenv("BOTIK_LEGACY_RUNTIME_LOG_PATH")
            else None,
            runtime_status_heartbeat_stale_seconds=float(os.getenv("BOTIK_RUNTIME_STATUS_STALE_SECONDS", "120.0")),
            runtime_status_fixture_path=Path(os.getenv("BOTIK_RUNTIME_STATUS_FIXTURE_PATH"))
            if os.getenv("BOTIK_RUNTIME_STATUS_FIXTURE_PATH")
            else None,
            runtime_control_mode=os.getenv("BOTIK_RUNTIME_CONTROL_MODE", "auto"),
            runtime_control_heartbeat_interval_seconds=float(
                os.getenv("BOTIK_RUNTIME_CONTROL_HEARTBEAT_SECONDS", "1.0")
            ),
            runtime_control_stop_timeout_seconds=float(os.getenv("BOTIK_RUNTIME_CONTROL_STOP_TIMEOUT_SECONDS", "8.0")),
            spot_read_fixture_db_path=Path(os.getenv("BOTIK_SPOT_READ_FIXTURE_DB_PATH"))
            if os.getenv("BOTIK_SPOT_READ_FIXTURE_DB_PATH")
            else None,
            spot_read_account_type=os.getenv("BOTIK_SPOT_READ_ACCOUNT_TYPE", "UNIFIED"),
            futures_read_fixture_db_path=Path(os.getenv("BOTIK_FUTURES_READ_FIXTURE_DB_PATH"))
            if os.getenv("BOTIK_FUTURES_READ_FIXTURE_DB_PATH")
            else None,
            futures_read_account_type=os.getenv("BOTIK_FUTURES_READ_ACCOUNT_TYPE", "UNIFIED"),
            telegram_ops_fixture_path=Path(os.getenv("BOTIK_TELEGRAM_OPS_FIXTURE_PATH"))
            if os.getenv("BOTIK_TELEGRAM_OPS_FIXTURE_PATH")
            else None,
        )
