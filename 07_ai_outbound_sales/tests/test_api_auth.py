"""Tests for the auth API endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    Base,
    Tenant,
    User,
    UserRole,
)
from dashboard.auth import (
    create_access_token,
    hash_password,
    verify_password,
    verify_token,
)


@pytest.fixture
async def auth_app(async_engine):
    """Create a FastAPI app with auth router for testing."""
    from fastapi import FastAPI
    from dashboard.auth import router as auth_router
    import dashboard.auth as auth_module

    app = FastAPI()
    app.include_router(auth_router)

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[auth_module._get_session] = override_get_session

    return app, session_factory


def test_hash_password_and_verify():
    """Test password hashing and verification."""
    password = "secure_password_123"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_create_and_verify_token():
    """Test JWT token creation and verification."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        token = create_access_token({"sub": user_id, "tenant_id": tenant_id})

        payload = verify_token(token)
        assert payload["sub"] == user_id
        assert payload["tenant_id"] == tenant_id


async def test_register_creates_user_and_tenant(auth_app):
    """Test register creates user+tenant (201)."""
    app, session_factory = auth_app

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.stripe_secret_key = ""

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "newuser@company.com",
                    "password": "strong_pass_123",
                    "tenant_name": "My Company",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@company.com"
    assert data["role"] == "admin"
    assert "tenant_id" in data


async def test_register_duplicate_email_returns_409(auth_app):
    """Test duplicate email returns 409."""
    app, session_factory = auth_app

    # First, create a user directly
    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(), name="Existing", domain="existing.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="existing@existing.com",
            password_hash=hash_password("password123"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.stripe_secret_key = ""

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "existing@existing.com",
                    "password": "password123",
                    "tenant_name": "Duplicate",
                },
            )

    assert response.status_code == 409


async def test_login_returns_jwt_token(auth_app):
    """Test login returns JWT token."""
    app, session_factory = auth_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(), name="Login Corp", domain="login.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="login@login.com",
            password_hash=hash_password("correct_password"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"email": "login@login.com", "password": "correct_password"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_invalid_credentials_return_401(auth_app):
    """Test invalid credentials return 401."""
    app, session_factory = auth_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(), name="Auth Corp", domain="auth.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="auth@auth.com",
            password_hash=hash_password("right_password"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"email": "auth@auth.com", "password": "wrong_password"},
            )

    assert response.status_code == 401


async def test_get_current_user_with_valid_token(auth_app):
    """Test token validation with get_current_user via a protected endpoint."""
    app, session_factory = auth_app

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    async with session_factory() as session:
        tenant = Tenant(
            id=tenant_id, name="Token Corp", domain="token.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="token@token.com",
            password_hash=hash_password("password"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        token = create_access_token({"sub": str(user_id), "tenant_id": str(tenant_id)})

        # Use the login endpoint as a way to confirm the token works.
        # The register endpoint uses auth, so we try to register with the same email
        # which should hit the 409 check (proving auth + DB work together).
        # Actually, let's just add a simple protected route to the test app.
        from fastapi import Depends
        from dashboard.auth import get_current_user

        @app.get("/api/test-me")
        async def test_me(current_user=Depends(get_current_user)):
            return {"id": str(current_user.id), "email": current_user.email}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/test-me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "token@token.com"


async def test_refresh_token_returns_new_token(auth_app):
    """Test refresh returns a new valid JWT."""
    app, session_factory = auth_app

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    async with session_factory() as session:
        tenant = Tenant(
            id=tenant_id, name="Refresh Corp", domain="refresh.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="refresh@refresh.com",
            password_hash=hash_password("password"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        token = create_access_token({"sub": str(user_id), "tenant_id": str(tenant_id)})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/refresh",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_get_me_returns_user_info(auth_app):
    """Test GET /api/auth/me returns current user info."""
    app, session_factory = auth_app

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    async with session_factory() as session:
        tenant = Tenant(
            id=tenant_id, name="Me Corp", domain="me.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="me@me.com",
            password_hash=hash_password("password"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        token = create_access_token({"sub": str(user_id), "tenant_id": str(tenant_id)})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@me.com"
    assert data["role"] == "admin"
