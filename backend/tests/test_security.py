"""Tests for security infrastructure: encryption, permissions, rate limiting."""

import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from cryptography.fernet import Fernet

from backend.app import create_app
from backend.database import Base, get_db

# Test database - in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

AUTH_HEADERS = {"Authorization": "Bearer change-me-in-production"}


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield application
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Encryption tests ---


class TestEncryption:
    """Test encryption module."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt should return original value."""
        # Set a test key
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key

        # Re-import to pick up the key
        from backend.security.encryption import encrypt_value, decrypt_value
        # Update settings in-place
        from backend import config
        config.settings.ENCRYPTION_KEY = key

        plaintext = "Sensitive data 12345"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

        # Cleanup
        config.settings.ENCRYPTION_KEY = ""
        os.environ.pop("ENCRYPTION_KEY", None)

    def test_encrypt_no_key_passthrough(self):
        """Without encryption key, values pass through unchanged."""
        from backend.security.encryption import encrypt_value, decrypt_value
        from backend import config
        config.settings.ENCRYPTION_KEY = ""

        plaintext = "plain text data"
        assert encrypt_value(plaintext) == plaintext
        assert decrypt_value(plaintext) == plaintext


# --- Permissions tests ---


class TestPermissions:
    """Test role-based access control."""

    @pytest.mark.asyncio
    async def test_admin_allowed_on_audit(self, client):
        """Admin role should be allowed to access audit endpoint."""
        headers = {**AUTH_HEADERS, "X-User-Role": "admin"}
        response = await client.get("/api/v1/audit", headers=headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_director_allowed_on_audit(self, client):
        """Director role should be allowed to access audit endpoint."""
        headers = {**AUTH_HEADERS, "X-User-Role": "director"}
        response = await client.get("/api/v1/audit", headers=headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cashier_rejected_on_audit(self, client):
        """Cashier role should be rejected from audit endpoint."""
        headers = {**AUTH_HEADERS, "X-User-Role": "cashier"}
        response = await client.get("/api/v1/audit", headers=headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_auth_rejected_on_audit(self, client):
        """No auth token should be rejected."""
        response = await client.get("/api/v1/audit")
        assert response.status_code == 401


# --- Health / Ready tests ---


class TestHealthReady:
    """Test enhanced health and readiness endpoints."""

    @pytest.mark.asyncio
    async def test_health_has_db_and_uptime(self, client):
        """Health endpoint should include db and uptime fields."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "db" in data
        assert "uptime" in data

    @pytest.mark.asyncio
    async def test_ready_endpoint(self, client):
        """Ready endpoint should return status ready."""
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
