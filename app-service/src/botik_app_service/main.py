import asyncio
import contextlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Repo root: next to the exe when frozen, or 3 dirs up from this file in dev mode
_REPO_ROOT: Path = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3]
)
# Frontend static dist (bundled inside exe or built locally)
_STATIC_ROOT: Path = (
    Path(getattr(sys, "_MEIPASS", "")) / "frontend" / "dist"
    if getattr(sys, "frozen", False)
    else _REPO_ROOT / "frontend" / "dist"
)

from botik_app_service.analytics_read.service import AnalyticsReadService
from botik_app_service.api.routes_analytics import router as analytics_router
from botik_app_service.api.routes_admin import router as admin_router
from botik_app_service.api.routes_bootstrap import router as bootstrap_router
from botik_app_service.api.routes_db_health import router as db_health_router
from botik_app_service.api.routes_diagnostics import router as diagnostics_router
from botik_app_service.api.routes_events import router as events_router
from botik_app_service.api.routes_futures import router as futures_router
from botik_app_service.api.routes_health import router as health_router
from botik_app_service.api.routes_jobs import router as jobs_router
from botik_app_service.api.routes_logs import router as logs_router
from botik_app_service.api.routes_backtest import router as backtest_router
from botik_app_service.api.routes_market import router as market_router
from botik_app_service.api.routes_models import router as models_router
from botik_app_service.api.routes_orderbook import router as orderbook_router
from botik_app_service.api.routes_reconciliation import router as reconciliation_router
from botik_app_service.api.routes_settings import router as settings_router
from botik_app_service.api.routes_spot import router as spot_router
from botik_app_service.api.routes_telegram import router as telegram_router
from botik_app_service.api.routes_runtime_control import router as runtime_control_router
from botik_app_service.api.routes_runtime_status import router as runtime_status_router
from botik_app_service.db_health.service import DbHealthService
from botik_app_service.diagnostics_compat.service import DiagnosticsCompatibilityService
from botik_app_service.futures_read.service import FuturesReadService
from botik_app_service.backtest_run.service import BacktestRunService
from botik_app_service.market_read.service import MarketReadService
from botik_app_service.orderbook_read.service import OrderbookReadService
from botik_app_service.reconciliation_read.manager import ReconciliationReadService
from botik_app_service.settings_read.service import SettingsReadService
from botik_app_service.infra.config import Settings
from botik_app_service.infra.logging import configure_logging
from botik_app_service.jobs.event_publisher import EventPublisher
from botik_app_service.jobs.data_backfill_job import create_data_backfill_job_definition
from botik_app_service.jobs.data_integrity_job import create_data_integrity_job_definition
from botik_app_service.jobs.manager import JobManager
from botik_app_service.jobs.process_adapter import ProcessAdapter
from botik_app_service.jobs.recovery_guard import RecoveryGuard
from botik_app_service.jobs.registry import JobRegistry
from botik_app_service.jobs.sample_data_job import create_sample_data_job_definition
from botik_app_service.jobs.store import JobStore
from botik_app_service.jobs.supervisor import JobSupervisor
from botik_app_service.jobs.training_control_job import create_training_control_job_definition
from botik_app_service.logs.manager import LogsManager
from botik_app_service.models_read.service import ModelsReadService
from botik_app_service.runtime_control.service import RuntimeControlService
from botik_app_service.runtime_status.service import RuntimeStatusService
from botik_app_service.spot_read.service import SpotReadService
from botik_app_service.telegram_ops.service import TelegramOpsService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    logger = configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        publisher = EventPublisher(buffer_size=resolved_settings.event_buffer_size)
        logs_manager = LogsManager(
            buffer_size=resolved_settings.log_channel_buffer_size,
            snapshot_limit=resolved_settings.log_snapshot_limit,
            artifacts_dir=resolved_settings.artifacts_dir,
            legacy_runtime_log_path=resolved_settings.legacy_runtime_log_path,
        )
        log_handler = logs_manager.create_capture_handler()
        logger.addHandler(log_handler)
        store = JobStore()
        registry = JobRegistry()
        process_adapter = ProcessAdapter()
        supervisor = JobSupervisor(process_adapter=process_adapter, store=store, publisher=publisher)
        recovery_guard = RecoveryGuard()
        manager = JobManager(registry=registry, store=store, supervisor=supervisor, publisher=publisher)
        runtime_control_service = RuntimeControlService(
            repo_root=_REPO_ROOT,
            process_adapter=process_adapter,
            mode=resolved_settings.runtime_control_mode,
            runtime_status_fixture_path=resolved_settings.runtime_status_fixture_path,
            artifacts_dir=resolved_settings.artifacts_dir,
            heartbeat_interval_seconds=resolved_settings.runtime_control_heartbeat_interval_seconds,
            stop_timeout_seconds=resolved_settings.runtime_control_stop_timeout_seconds,
        )
        registry.register(create_sample_data_job_definition())
        registry.register(create_data_backfill_job_definition())
        registry.register(create_data_integrity_job_definition())
        registry.register(
            create_training_control_job_definition(
                fixture_db_path=resolved_settings.models_read_fixture_db_path,
                manifest_path=resolved_settings.models_read_manifest_path,
            )
        )
        runtime_status_service = RuntimeStatusService(
            repo_root=_REPO_ROOT,
            heartbeat_stale_seconds=resolved_settings.runtime_status_heartbeat_stale_seconds,
            fixture_path=resolved_settings.runtime_status_fixture_path,
            observation_provider=runtime_control_service,
        )
        spot_read_service = SpotReadService(
            repo_root=_REPO_ROOT,
            account_type=resolved_settings.spot_read_account_type,
            fixture_db_path=resolved_settings.spot_read_fixture_db_path,
        )
        futures_read_service = FuturesReadService(
            repo_root=_REPO_ROOT,
            account_type=resolved_settings.futures_read_account_type,
            fixture_db_path=resolved_settings.futures_read_fixture_db_path,
        )
        telegram_ops_service = TelegramOpsService(
            repo_root=_REPO_ROOT,
            fixture_path=resolved_settings.telegram_ops_fixture_path,
        )
        analytics_read_service = AnalyticsReadService(
            repo_root=_REPO_ROOT,
            fixture_db_path=resolved_settings.analytics_read_fixture_db_path,
        )
        diagnostics_service = DiagnosticsCompatibilityService(
            repo_root=_REPO_ROOT,
            settings=resolved_settings,
        )
        models_read_service = ModelsReadService(
            repo_root=_REPO_ROOT,
            fixture_db_path=resolved_settings.models_read_fixture_db_path,
            manifest_path=resolved_settings.models_read_manifest_path,
        )
        settings_read_service = SettingsReadService(
            repo_root=_REPO_ROOT,
        )
        market_read_service = MarketReadService(
            repo_root=_REPO_ROOT,
        )
        orderbook_read_service = OrderbookReadService(
            repo_root=_REPO_ROOT,
        )
        backtest_run_service = BacktestRunService(
            repo_root=_REPO_ROOT,
        )
        reconciliation_read_service = ReconciliationReadService(
            repo_root=_REPO_ROOT,
        )
        db_health_service = DbHealthService(
            repo_root=_REPO_ROOT,
        )
        await logs_manager.start(publisher)

        app.state.settings = resolved_settings
        app.state.logger = logger
        app.state.event_publisher = publisher
        app.state.logs_manager = logs_manager
        app.state.runtime_status_service = runtime_status_service
        app.state.runtime_control_service = runtime_control_service
        app.state.spot_read_service = spot_read_service
        app.state.futures_read_service = futures_read_service
        app.state.telegram_ops_service = telegram_ops_service
        app.state.analytics_read_service = analytics_read_service
        app.state.diagnostics_service = diagnostics_service
        app.state.models_read_service = models_read_service
        app.state.settings_read_service = settings_read_service
        app.state.market_read_service = market_read_service
        app.state.orderbook_read_service = orderbook_read_service
        app.state.backtest_run_service = backtest_run_service
        app.state.reconciliation_read_service = reconciliation_read_service
        app.state.db_health_service = db_health_service
        app.state.job_store = store
        app.state.job_registry = registry
        app.state.job_manager = manager
        app.state.recovery_guard = recovery_guard

        await recovery_guard.scan_orphans()
        heartbeat_task = asyncio.create_task(publisher.run_heartbeat(resolved_settings.sse_heartbeat_interval_seconds))
        app.state.heartbeat_task = heartbeat_task
        logger.info("Botik app-service started with unified logs support.")
        try:
            yield
        finally:
            logger.info("Botik app-service shutdown requested.")
            publisher.stop()
            await runtime_control_service.shutdown()
            await manager.shutdown()
            await logs_manager.stop()
            logger.removeHandler(log_handler)
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    app = FastAPI(
        title="Botik Foundation App Service",
        version=resolved_settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["x-botik-session-token", "content-type"],
    )

    app.include_router(health_router)
    app.include_router(bootstrap_router)
    app.include_router(jobs_router)
    app.include_router(events_router)
    app.include_router(logs_router)
    app.include_router(runtime_status_router)
    app.include_router(runtime_control_router)
    app.include_router(spot_router)
    app.include_router(futures_router)
    app.include_router(telegram_router)
    app.include_router(analytics_router)
    app.include_router(diagnostics_router)
    app.include_router(models_router)
    app.include_router(settings_router)
    app.include_router(market_router)
    app.include_router(orderbook_router)
    app.include_router(backtest_router)
    app.include_router(reconciliation_router)
    app.include_router(db_health_router)
    app.include_router(admin_router)

    # Serve compiled frontend (production/exe mode)
    if _STATIC_ROOT.exists():
        if (_STATIC_ROOT / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(_STATIC_ROOT / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request) -> FileResponse:
            return FileResponse(str(_STATIC_ROOT / "index.html"))

    return app


app = create_app()
