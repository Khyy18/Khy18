"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import Base, engine
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
)
from backend.ai.router import router as ai_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Kindergarten Accountant API",
        description="REST API for kindergarten accounting operations",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    app.include_router(ai_router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
