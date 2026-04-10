import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from botik_app_service.api.routes_admin import router as admin_router
from botik_app_service.api.routes_bootstrap import router as bootstrap_router
from botik_app_service.api.routes_events import router as events_router
from botik_app_service.api.routes_health import router as health_router
from botik_app_service.api.routes_jobs import router as jobs_router
from botik_app_service.infra.config import Settings
from botik_app_service.infra.logging import configure_logging
from botik_app_service.jobs.event_publisher import EventPublisher
from botik_app_service.jobs.manager import JobManager
from botik_app_service.jobs.process_adapter import ProcessAdapter
from botik_app_service.jobs.recovery_guard import RecoveryGuard
from botik_app_service.jobs.registry import JobRegistry
from botik_app_service.jobs.sample_data_job import create_sample_data_job_definition
from botik_app_service.jobs.store import JobStore
from botik_app_service.jobs.supervisor import JobSupervisor


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    logger = configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        publisher = EventPublisher(buffer_size=resolved_settings.event_buffer_size)
        store = JobStore()
        registry = JobRegistry()
        process_adapter = ProcessAdapter()
        supervisor = JobSupervisor(process_adapter=process_adapter, store=store, publisher=publisher)
        recovery_guard = RecoveryGuard()
        manager = JobManager(registry=registry, store=store, supervisor=supervisor, publisher=publisher)
        registry.register(create_sample_data_job_definition())

        app.state.settings = resolved_settings
        app.state.logger = logger
        app.state.event_publisher = publisher
        app.state.job_store = store
        app.state.job_registry = registry
        app.state.job_manager = manager
        app.state.recovery_guard = recovery_guard

        await recovery_guard.scan_orphans()
        heartbeat_task = asyncio.create_task(publisher.run_heartbeat(resolved_settings.sse_heartbeat_interval_seconds))
        app.state.heartbeat_task = heartbeat_task
        try:
            yield
        finally:
            publisher.stop()
            await manager.shutdown()
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    import contextlib

    app = FastAPI(
        title="Botik Foundation App Service",
        version=resolved_settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.frontend_url],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["x-botik-session-token", "content-type"],
    )

    app.include_router(health_router)
    app.include_router(bootstrap_router)
    app.include_router(jobs_router)
    app.include_router(events_router)
    app.include_router(admin_router)
    return app


app = create_app()
