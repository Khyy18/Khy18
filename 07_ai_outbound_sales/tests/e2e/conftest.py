"""Shared fixtures for E2E API tests.

Uses httpx AsyncClient with ASGITransport to test the FastAPI app
with a real SQLite in-memory database and mocked external services.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.models import Base


@pytest.fixture
async def e2e_engine():
    """Create an async in-memory SQLite engine for E2E testing."""
    from sqlalchemy import TypeDecorator, String as SAString
    import uuid as _uuid_mod

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    class SQLiteUUID(TypeDecorator):
        impl = SAString(36)
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, _uuid_mod.UUID):
                return str(value)
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, _uuid_mod.UUID):
                return value
            return _uuid_mod.UUID(value)

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, PG_UUID):
                column.type = SQLiteUUID()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def e2e_session_factory(e2e_engine):
    """Return a session factory bound to the E2E in-memory engine."""
    return async_sessionmaker(
        e2e_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def e2e_app(e2e_session_factory):
    """Create a FastAPI app configured for E2E testing.

    Overrides database session dependencies for all routers so that
    the app uses the test SQLite database.
    """
    from fastapi import FastAPI

    import dashboard.auth as auth_module
    import dashboard.routes.campaigns as campaigns_module
    import dashboard.routes.leads as leads_module
    import dashboard.routes.onboarding as onboarding_module
    import dashboard.routes.voice as voice_module
    import dashboard.routes.billing as billing_module
    import dashboard.routes.analytics as analytics_module

    from dashboard.auth import router as auth_router
    from dashboard.routes.campaigns import router as campaigns_router
    from dashboard.routes.leads import router as leads_router
    from dashboard.routes.onboarding import router as onboarding_router
    from dashboard.routes.voice import router as voice_router
    from dashboard.routes.billing import router as billing_router
    from dashboard.routes.analytics import router as analytics_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(campaigns_router)
    app.include_router(leads_router)
    app.include_router(onboarding_router)
    app.include_router(voice_router)
    app.include_router(billing_router)
    app.include_router(analytics_router)

    # Add health endpoint
    from fastapi.responses import JSONResponse

    @app.get("/health")
    async def health_check():
        return JSONResponse(
            content={"status": "healthy", "version": "0.1.0"},
            status_code=200,
        )

    async def override_get_session():
        async with e2e_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override all _get_session dependencies
    app.dependency_overrides[auth_module._get_session] = override_get_session
    app.dependency_overrides[campaigns_module._get_session] = override_get_session
    app.dependency_overrides[leads_module._get_session] = override_get_session
    app.dependency_overrides[onboarding_module._get_session] = override_get_session
    app.dependency_overrides[voice_module._get_session] = override_get_session
    app.dependency_overrides[billing_module._get_session] = override_get_session
    app.dependency_overrides[analytics_module._get_session] = override_get_session

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
async def client(e2e_app):
    """Provide an httpx AsyncClient configured for the E2E app."""
    transport = ASGITransport(app=e2e_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def registered_user(client):
    """Register a test user and return the registration response data."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.stripe_secret_key = ""

        response = await client.post(
            "/api/auth/register",
            json={
                "email": f"e2e-{uuid.uuid4().hex[:8]}@testcorp.com",
                "password": "secure_pass_123",
                "tenant_name": "E2E Test Corp",
            },
        )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def auth_token(client, registered_user):
    """Login with the registered user and return the access token."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/auth/login",
            json={
                "email": registered_user["email"],
                "password": "secure_pass_123",
            },
        )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return authorization headers with the test user's token."""
    return {"Authorization": f"Bearer {auth_token}"}
