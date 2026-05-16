"""FastAPI application factory."""

import asyncio
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from backend.config import settings
from backend.database import Base, engine, async_session
from backend.logging_config import configure_logging
from backend.rate_limiter import limiter
from backend.routers import (
    employees,
    children,
    timesheet,
    journal,
    salary,
    vacation,
    sick,
    payments,
    reminders,
    kbk,
    calendar,
    notifications,
)
from backend.routers import admin as admin_router
from backend.routers import audit as audit_router
from backend.routers import downloads as downloads_router
from backend.ai.router import router as ai_router

# Configure structlog
configure_logging()

# Track app start time for uptime
_app_start_time: float = time.time()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Kindergarten Accountant API",
        description="REST API for kindergarten accounting operations",
        version="1.0.0",
    )

    # Rate limiter state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS - use explicit origins (never wildcard with credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Audit middleware
    from backend.middleware.audit import AuditMiddleware
    app.add_middleware(AuditMiddleware)

    # Metrics middleware
    from backend.middleware.metrics import MetricsMiddleware
    app.add_middleware(MetricsMiddleware)

    # Include routers with /api/v1 prefix
    app.include_router(employees.router, prefix="/api/v1")
    app.include_router(children.router, prefix="/api/v1")
    app.include_router(timesheet.router, prefix="/api/v1")
    app.include_router(journal.router, prefix="/api/v1")
    app.include_router(salary.router, prefix="/api/v1")
    app.include_router(vacation.router, prefix="/api/v1")
    app.include_router(sick.router, prefix="/api/v1")
    app.include_router(payments.router, prefix="/api/v1")
    app.include_router(reminders.router, prefix="/api/v1")
    app.include_router(kbk.router, prefix="/api/v1")
    app.include_router(calendar.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(admin_router.router, prefix="/api/v1")
    app.include_router(audit_router.router, prefix="/api/v1")
    app.include_router(downloads_router.router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Start background cleanup task for downloads
        asyncio.create_task(downloads_router._cleanup_expired())
        # Initialize Sentry if DSN is configured
        _init_sentry()

    @app.get("/health")
    async def health():
        """Health check with DB status and uptime."""
        db_status = "connected"
        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            db_status = "disconnected"

        uptime = round(time.time() - _app_start_time, 2)
        return {"status": "ok", "db": db_status, "uptime": uptime}

    @app.get("/ready")
    async def readiness():
        """Readiness probe - checks actual DB connectivity."""
        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ready"}
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "detail": str(e)},
            )

    return app


def _init_sentry():
    """Initialize Sentry SDK if SENTRY_DSN is configured."""
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                integrations=[
                    StarletteIntegration(),
                    FastApiIntegration(),
                ],
                traces_sample_rate=0.1,
            )
        except Exception:
            pass


app = create_app()
