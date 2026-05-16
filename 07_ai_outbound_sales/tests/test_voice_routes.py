"""Tests for voice dashboard API routes and webhooks."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    Call,
    CallScript,
    CallStatus,
    CallOutcome,
    Tenant,
    User,
    UserRole,
)
from dashboard.auth import create_access_token, hash_password


@pytest.fixture
async def voice_app(async_engine):
    """Create a minimal FastAPI app with voice routes for testing."""
    from fastapi import FastAPI
    from dashboard.routes.voice import router as voice_router
    from dashboard.routes.voice_webhooks import router as voice_webhooks_router
    from dashboard.auth import router as auth_router
    import dashboard.auth as auth_module
    import dashboard.routes.voice as voice_module

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(voice_router)
    app.include_router(voice_webhooks_router)

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    # Override _get_session dependencies
    app.dependency_overrides[auth_module._get_session] = override_get_session
    app.dependency_overrides[voice_module._get_session] = override_get_session

    return app, session_factory


@pytest.fixture
async def seeded_voice_data(voice_app):
    """Seed the database with a tenant, user, and some call data."""
    app, session_factory = voice_app
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    async with session_factory() as session:
        from tests.conftest import make_tenant, make_lead

        tenant = make_tenant(id=tenant_id, name="Voice Tenant", domain="voice.test")
        session.add(tenant)

        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="voiceuser@voice.test",
            password_hash=hash_password("testpass"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)

        lead = make_lead(id=lead_id, tenant_id=tenant_id)
        session.add(lead)
        await session.flush()

        # Add some calls
        call1 = Call(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lead_id=lead_id,
            twilio_sid="CA_test_001",
            status=CallStatus.completed,
            duration_seconds=60,
            outcome=CallOutcome.qualified,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        call2 = Call(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lead_id=lead_id,
            twilio_sid="CA_test_002",
            status=CallStatus.initiated,
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([call1, call2])

        # Add a script
        script = CallScript(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name="Test Script",
            script_json={"greeting_template": "Hello!"},
            voice_id="default",
            language="en",
            created_at=datetime.now(timezone.utc),
        )
        session.add(script)
        await session.commit()

    token = create_access_token({"sub": str(user_id), "tenant_id": str(tenant_id)})
    return {
        "app": app,
        "session_factory": session_factory,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "lead_id": lead_id,
        "token": token,
        "call1_id": str(call1.id),
        "call2_id": str(call2.id),
        "script_id": str(script.id),
    }


async def test_list_calls_returns_200(seeded_voice_data):
    """Test GET /api/voice/calls returns 200 with a list of calls."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/voice/calls",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "calls" in body
    assert "total" in body
    assert body["total"] == 2
    assert len(body["calls"]) == 2


async def test_get_call_detail_returns_call(seeded_voice_data):
    """Test GET /api/voice/calls/{id} returns call detail."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]
    call_id = data["call1_id"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/voice/calls/{call_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == call_id
    assert body["twilio_sid"] == "CA_test_001"


async def test_get_call_detail_returns_404_for_nonexistent(seeded_voice_data):
    """Test GET /api/voice/calls/{id} returns 404 for a nonexistent call."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]
    fake_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/voice/calls/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404


async def test_get_stats_returns_stats_dict(seeded_voice_data):
    """Test GET /api/voice/stats returns stats dictionary."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/voice/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "total_calls" in body
    assert "answered_count" in body
    assert "avg_duration_seconds" in body
    assert "outcomes" in body
    assert "conversion_rate" in body


async def test_create_script_returns_201(seeded_voice_data):
    """Test POST /api/voice/scripts creates a new script."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]

    payload = {
        "name": "New Script",
        "script_json": {"greeting_template": "Hi there!"},
        "voice_id": "voice_abc",
        "language": "en",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/voice/scripts",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Script"
    assert body["voice_id"] == "voice_abc"
    assert "id" in body


async def test_list_scripts_returns_list(seeded_voice_data):
    """Test GET /api/voice/scripts returns a list of scripts."""
    data = seeded_voice_data
    app = data["app"]
    token = data["token"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/voice/scripts",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["name"] == "Test Script"


async def test_twilio_status_webhook_updates_call(seeded_voice_data):
    """Test POST /api/voice/twilio/status updates call via call_manager."""
    data = seeded_voice_data
    app = data["app"]

    # Set up a mock call_manager on app.state
    mock_call_manager = AsyncMock()
    mock_call_manager.handle_status_update = AsyncMock()
    app.state.call_manager = mock_call_manager

    # Patch settings to have no auth token so signature validation is skipped
    with patch("core.config.settings") as mock_settings:
        mock_settings.twilio_auth_token = ""

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/voice/twilio/status",
                data={
                    "CallSid": "CA_test_001",
                    "CallStatus": "completed",
                    "CallDuration": "120",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    mock_call_manager.handle_status_update.assert_called_once_with(
        call_sid="CA_test_001",
        status="completed",
        duration=120,
    )
