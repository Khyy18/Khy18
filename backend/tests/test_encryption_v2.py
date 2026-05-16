"""Tests for AES-256-GCM encryption with versioned key rotation."""

import base64
import os

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db

# Test database - in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

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


def _generate_key() -> str:
    """Generate a base64-encoded 32-byte key for AES-256."""
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def setup_v1_key(monkeypatch):
    """Configure a V1 encryption key."""
    key = _generate_key()
    from backend import config

    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", key)
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", "")
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 1)
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
    return key


@pytest.fixture
def setup_v1_v2_keys(monkeypatch):
    """Configure V1 and V2 encryption keys with V2 as current."""
    key_v1 = _generate_key()
    key_v2 = _generate_key()
    from backend import config

    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", key_v1)
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", key_v2)
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 2)
    monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
    return key_v1, key_v2


class TestAES256GCMEncryption:
    """Test AES-256-GCM encrypt/decrypt."""

    def test_encrypt_decrypt_roundtrip(self, setup_v1_key):
        """Encrypt then decrypt should return original value."""
        from backend.security.encryption import encrypt_value, decrypt_value

        plaintext = "Sensitive employee name"
        encrypted = encrypt_value(plaintext)

        # Should have version prefix
        assert encrypted.startswith("v1:")
        assert encrypted != plaintext

        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_encrypt_uses_random_nonce(self, setup_v1_key):
        """Each encryption produces different ciphertext due to random nonce."""
        from backend.security.encryption import encrypt_value

        plaintext = "Same data"
        enc1 = encrypt_value(plaintext)
        enc2 = encrypt_value(plaintext)
        # Different nonces mean different ciphertexts
        assert enc1 != enc2

    def test_encrypt_field_directly(self, setup_v1_key):
        """Test encrypt_field/decrypt_field low-level functions."""
        from backend.security.encryption import decrypt_field, encrypt_field

        key = base64.b64decode(setup_v1_key)
        plaintext = "Direct field test"
        encrypted = encrypt_field(plaintext, key)
        decrypted = decrypt_field(encrypted, key)
        assert decrypted == plaintext

    def test_nonce_is_12_bytes(self, setup_v1_key):
        """Verify nonce is 12 bytes in encrypted output."""
        from backend.security.encryption import encrypt_field

        key = base64.b64decode(setup_v1_key)
        encrypted = encrypt_field("test", key)
        raw = base64.b64decode(encrypted)
        # At least 12 bytes nonce + some ciphertext + 16 byte tag
        assert len(raw) >= 12 + 1 + 16


class TestVersionedDecryption:
    """Test versioned key decryption."""

    def test_v1_data_decrypted_when_v2_is_current(self, setup_v1_v2_keys):
        """Data encrypted with V1 should still be decryptable when V2 is current."""
        from backend.security.encryption import (
            _get_key,
            decrypt_value,
            encrypt_field,
        )

        key_v1_bytes = _get_key(1)
        # Manually encrypt with v1
        plaintext = "Old data from v1"
        encrypted_data = encrypt_field(plaintext, key_v1_bytes)
        v1_ciphertext = f"v1:{encrypted_data}"

        # Now decrypt - should use v1 key even though current version is 2
        decrypted = decrypt_value(v1_ciphertext)
        assert decrypted == plaintext

    def test_v2_encryption_uses_v2_key(self, setup_v1_v2_keys):
        """encrypt_value should use the current version (V2) key."""
        from backend.security.encryption import encrypt_value

        encrypted = encrypt_value("New data")
        assert encrypted.startswith("v2:")

    def test_decrypt_v2_data(self, setup_v1_v2_keys):
        """V2 encrypted data should be decryptable."""
        from backend.security.encryption import decrypt_value, encrypt_value

        plaintext = "V2 encrypted data"
        encrypted = encrypt_value(plaintext)
        assert encrypted.startswith("v2:")
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext


class TestLegacyFallback:
    """Test backward compatibility with legacy Fernet data and plain text."""

    def test_plain_text_passthrough(self, monkeypatch):
        """Plain text without version prefix passes through when no Fernet key."""
        from backend import config
        from backend.security.encryption import decrypt_value

        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 1)

        plain = "Just a name"
        assert decrypt_value(plain) == plain

    def test_fernet_legacy_decrypt(self, monkeypatch):
        """Legacy Fernet-encrypted data should be decryptable via fallback."""
        from backend import config
        from backend.security.encryption import decrypt_value

        fernet_key = Fernet.generate_key().decode()
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", fernet_key)
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 1)

        # Encrypt with Fernet directly (simulating legacy data)
        f = Fernet(fernet_key.encode())
        plaintext = "Legacy encrypted name"
        legacy_ciphertext = f.encrypt(plaintext.encode()).decode()

        # decrypt_value should handle it via Fernet fallback
        decrypted = decrypt_value(legacy_ciphertext)
        assert decrypted == plaintext

    def test_empty_string_passthrough(self, monkeypatch):
        """Empty string should pass through."""
        from backend import config
        from backend.security.encryption import decrypt_value

        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", "")
        assert decrypt_value("") == ""


class TestNoKeyPassthrough:
    """Test dev mode when no keys are configured."""

    def test_encrypt_no_key_passthrough(self, monkeypatch):
        """Without any encryption key, values pass through unchanged."""
        from backend import config
        from backend.security.encryption import decrypt_value, encrypt_value

        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 1)

        plaintext = "dev mode data"
        assert encrypt_value(plaintext) == plaintext
        assert decrypt_value(plaintext) == plaintext


class TestRotateKeyEndpoint:
    """Test the admin key rotation endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_key_re_encrypts_records(self, client, monkeypatch):
        """POST /api/v1/admin/rotate-key should re-encrypt all records."""
        from backend import config

        key_v1 = _generate_key()
        key_v2 = _generate_key()

        # Start with V1 as current to create records
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", "")
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 1)
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")

        # Create an employee (fio gets encrypted with v1)
        headers = {**AUTH_HEADERS, "X-User-Role": "admin"}
        resp = await client.post(
            "/api/v1/employees",
            json={"fio": "Test Employee", "position": "Teacher", "rate": 1.0},
            headers=headers,
        )
        assert resp.status_code == 201

        # Create a child (child_fio and parent_fio get encrypted with v1)
        resp = await client.post(
            "/api/v1/children",
            json={
                "child_fio": "Child Name",
                "group_name": "Group A",
                "parent_fio": "Parent Name",
                "discount_percent": 0,
            },
            headers=headers,
        )
        assert resp.status_code == 201

        # Now switch to V2 as current version
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_V2", key_v2)
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY_VERSION", 2)

        # Call rotate-key endpoint
        resp = await client.post(
            "/api/v1/admin/rotate-key",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        # 1 employee fio + 1 child_fio + 1 parent_fio = 3
        assert data["re_encrypted_fields"] == 3

    @pytest.mark.asyncio
    async def test_rotate_key_requires_admin(self, client):
        """Non-admin role should be rejected."""
        headers = {**AUTH_HEADERS, "X-User-Role": "cashier"}
        resp = await client.post("/api/v1/admin/rotate-key", headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rotate_key_requires_auth(self, client):
        """No auth should be rejected."""
        resp = await client.post("/api/v1/admin/rotate-key")
        assert resp.status_code == 401
