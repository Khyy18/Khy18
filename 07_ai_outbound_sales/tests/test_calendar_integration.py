"""Tests for calendar integration: CalendlyClient, CalendarManager, and calendar API routes."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import Response, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Tenant, User, UserRole
from integrations.calendly import CalendlyClient
from integrations.calendar import CalendarManager, GoogleCalendarClient


# ---------- CalendlyClient Tests ----------


async def test_calendly_get_available_slots_success():
    """CalendlyClient.get_available_slots returns slot list on success."""
    client = CalendlyClient(api_key="test-key")

    mock_response = Response(
        200,
        json={
            "collection": [
                {"start_time": "2024-01-15T10:00:00Z", "status": "available"},
                {"start_time": "2024-01-15T11:00:00Z", "status": "available"},
            ]
        },
        request=Request("GET", "https://api.calendly.com/event_type_available_times"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        slots = await client.get_available_slots(
            event_type_uri="https://api.calendly.com/event_types/123",
            start_date="2024-01-15T00:00:00Z",
            end_date="2024-01-16T00:00:00Z",
        )

    assert len(slots) == 2
    assert slots[0]["start_time"] == "2024-01-15T10:00:00Z"
    assert slots[0]["status"] == "available"


async def test_calendly_get_available_slots_empty_key():
    """CalendlyClient returns empty list when API key is not set."""
    client = CalendlyClient(api_key="")
    slots = await client.get_available_slots(
        event_type_uri="https://api.calendly.com/event_types/123",
        start_date="2024-01-15T00:00:00Z",
        end_date="2024-01-16T00:00:00Z",
    )
    assert slots == []


async def test_calendly_get_available_slots_http_error():
    """CalendlyClient returns empty list on HTTP error."""
    client = CalendlyClient(api_key="test-key")

    mock_response = Response(
        401,
        json={"error": "Unauthorized"},
        request=Request("GET", "https://api.calendly.com/event_type_available_times"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        slots = await client.get_available_slots(
            event_type_uri="https://api.calendly.com/event_types/123",
            start_date="2024-01-15T00:00:00Z",
            end_date="2024-01-16T00:00:00Z",
        )

    assert slots == []


async def test_calendly_create_booking_success():
    """CalendlyClient.create_booking returns booking confirmation on success."""
    client = CalendlyClient(api_key="test-key")

    mock_response = Response(
        201,
        json={
            "resource": {
                "uri": "https://api.calendly.com/scheduled_events/abc123",
            }
        },
        request=Request("POST", "https://api.calendly.com/scheduled_events"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.create_booking(
            event_type_uri="https://api.calendly.com/event_types/123",
            invitee_email="lead@example.com",
            invitee_name="John Doe",
            start_time="2024-01-15T10:00:00Z",
        )

    assert result["status"] == "booked"
    assert result["invitee_email"] == "lead@example.com"
    assert "uri" in result


async def test_calendly_create_booking_empty_key():
    """CalendlyClient.create_booking returns error when API key is not set."""
    client = CalendlyClient(api_key="")
    result = await client.create_booking(
        event_type_uri="https://api.calendly.com/event_types/123",
        invitee_email="lead@example.com",
        invitee_name="John Doe",
        start_time="2024-01-15T10:00:00Z",
    )
    assert "error" in result


# ---------- GoogleCalendarClient Tests ----------


async def test_google_calendar_get_oauth_url():
    """GoogleCalendarClient generates correct OAuth URL."""
    client = GoogleCalendarClient(
        client_id="test-client-id",
        client_secret="test-secret",
    )
    url = client.get_oauth_url(state="test-state")
    assert "accounts.google.com" in url
    assert "test-client-id" in url
    assert "test-state" in url
    assert "calendar" in url


async def test_google_calendar_check_availability_no_token():
    """GoogleCalendarClient returns empty list without access token."""
    client = GoogleCalendarClient(
        client_id="test-id",
        client_secret="test-secret",
    )
    result = await client.check_availability(
        start_date="2024-01-15T00:00:00Z",
        end_date="2024-01-16T00:00:00Z",
    )
    assert result == []


async def test_google_calendar_create_event_no_token():
    """GoogleCalendarClient returns error dict without access token."""
    client = GoogleCalendarClient(
        client_id="test-id",
        client_secret="test-secret",
    )
    result = await client.create_event(
        title="Demo Call",
        start_time="2024-01-15T10:00:00Z",
        end_time="2024-01-15T10:30:00Z",
        attendees=["lead@example.com"],
    )
    assert "error" in result


async def test_google_calendar_set_tokens():
    """GoogleCalendarClient.set_tokens updates internal state."""
    client = GoogleCalendarClient(
        client_id="test-id",
        client_secret="test-secret",
    )
    client.set_tokens("access-123", "refresh-456")
    assert client._access_token == "access-123"
    assert client._refresh_token == "refresh-456"


# ---------- CalendarManager Tests ----------


async def test_calendar_manager_routes_to_calcom():
    """CalendarManager routes calls to Cal.com provider."""
    manager = CalendarManager(
        provider="calcom",
        calcom_api_key="test-key",
    )
    assert manager.provider == "calcom"
    assert manager.validate_api_key() is True


async def test_calendar_manager_routes_to_google():
    """CalendarManager routes calls to Google provider."""
    manager = CalendarManager(
        provider="google",
        google_client_id="id",
        google_client_secret="secret",
    )
    assert manager.provider == "google"
    assert manager.validate_api_key() is True
    url = manager.get_oauth_url(state="test")
    assert url is not None
    assert "accounts.google.com" in url


async def test_calendar_manager_routes_to_calendly():
    """CalendarManager routes calls to Calendly provider."""
    manager = CalendarManager(
        provider="calendly",
        calendly_api_key="test-key",
        calendly_event_type="https://api.calendly.com/event_types/123",
    )
    assert manager.provider == "calendly"
    assert manager.validate_api_key() is True


async def test_calendar_manager_validate_missing_key():
    """CalendarManager.validate_api_key returns False when key is empty."""
    manager = CalendarManager(provider="calcom", calcom_api_key="")
    assert manager.validate_api_key() is False


async def test_calendar_manager_unsupported_provider():
    """CalendarManager with unsupported provider validates as False."""
    manager = CalendarManager(provider="unknown")
    assert manager.validate_api_key() is False


# ---------- Calendar Route Tests ----------


async def test_calendar_connect_google(async_session: AsyncSession, session_factory):
    """POST /api/integrations/calendar/connect returns OAuth URL for Google."""
    from fastapi import FastAPI
    from dashboard.auth import get_current_user
    from dashboard.routes.calendar import router, _get_session

    app = FastAPI()
    app.include_router(router)

    tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="test@test.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )

    async def _override_user():
        return user

    async def _override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_get_session] = _override_session

    with patch("dashboard.routes.calendar.settings") as mock_settings:
        mock_settings.calendar_provider = "calcom"
        mock_settings.calcom_api_key = ""
        mock_settings.calcom_base_url = "https://api.cal.com/v1"
        mock_settings.google_calendar_client_id = "test-client-id"
        mock_settings.google_calendar_client_secret = "test-secret"
        mock_settings.calendly_api_key = ""
        mock_settings.calendly_event_type = ""

        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/integrations/calendar/connect",
                json={"provider": "google"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "oauth_required"
    assert "oauth_url" in data
    assert "google" in data["oauth_url"]


async def test_calendar_connect_calendly_success(async_session: AsyncSession, session_factory):
    """POST /api/integrations/calendar/connect returns success for Calendly with valid key."""
    from fastapi import FastAPI
    from dashboard.auth import get_current_user
    from dashboard.routes.calendar import router, _get_session

    app = FastAPI()
    app.include_router(router)

    tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="test@test.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )

    async def _override_user():
        return user

    async def _override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_get_session] = _override_session

    with patch("dashboard.routes.calendar.settings") as mock_settings:
        mock_settings.calendar_provider = "calcom"
        mock_settings.calcom_api_key = ""
        mock_settings.calcom_base_url = "https://api.cal.com/v1"
        mock_settings.google_calendar_client_id = ""
        mock_settings.google_calendar_client_secret = ""
        mock_settings.calendly_api_key = "test-calendly-key"
        mock_settings.calendly_event_type = "https://api.calendly.com/event_types/123"

        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/integrations/calendar/connect",
                json={"provider": "calendly"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["provider"] == "calendly"


async def test_calendar_connect_unsupported_provider(async_session: AsyncSession, session_factory):
    """POST /api/integrations/calendar/connect returns 400 for unsupported provider."""
    from fastapi import FastAPI
    from dashboard.auth import get_current_user
    from dashboard.routes.calendar import router, _get_session

    app = FastAPI()
    app.include_router(router)

    tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="test@test.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )

    async def _override_user():
        return user

    async def _override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_get_session] = _override_session

    with patch("dashboard.routes.calendar.settings") as mock_settings:
        mock_settings.calendar_provider = "calcom"
        mock_settings.calcom_api_key = ""
        mock_settings.calcom_base_url = "https://api.cal.com/v1"
        mock_settings.google_calendar_client_id = ""
        mock_settings.google_calendar_client_secret = ""
        mock_settings.calendly_api_key = ""
        mock_settings.calendly_event_type = ""

        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/integrations/calendar/connect",
                json={"provider": "outlook"},
            )

    assert response.status_code == 400


async def test_calendar_availability_endpoint(async_session: AsyncSession, session_factory):
    """GET /api/integrations/calendar/availability returns slots."""
    from fastapi import FastAPI
    from dashboard.auth import get_current_user
    from dashboard.routes.calendar import router, _get_session, _get_calendar_manager

    app = FastAPI()
    app.include_router(router)

    tenant_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="test@test.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )

    async def _override_user():
        return user

    async def _override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_get_session] = _override_session

    mock_slots = [{"start": "2024-01-15T10:00:00Z", "end": "2024-01-15T10:30:00Z"}]

    mock_manager = AsyncMock()
    mock_manager.validate_api_key.return_value = True
    mock_manager.provider = "calcom"
    mock_manager.check_availability = AsyncMock(return_value=mock_slots)

    with patch("dashboard.routes.calendar._get_calendar_manager", return_value=mock_manager):
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/integrations/calendar/availability",
                params={
                    "start_date": "2024-01-15T00:00:00Z",
                    "end_date": "2024-01-16T00:00:00Z",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "calcom"
    assert len(data["slots"]) == 1
    assert data["slots"][0]["start"] == "2024-01-15T10:00:00Z"
