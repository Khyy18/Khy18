"""E2E tests for the voice channel flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_create_call_script(client, auth_headers):
    """Test creating a new call script."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/voice/scripts",
            json={
                "name": "Demo Script",
                "script_json": {
                    "greeting_template": "Hello {first_name}!",
                    "topics": ["product demo", "pricing"],
                },
                "voice_id": "voice_abc123",
                "language": "en",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Demo Script"
    assert data["script_json"]["greeting_template"] == "Hello {first_name}!"
    assert data["voice_id"] == "voice_abc123"
    assert data["language"] == "en"
    assert "id" in data


async def test_list_call_scripts(client, auth_headers):
    """Test listing call scripts after creating one."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Create a script
        await client.post(
            "/api/voice/scripts",
            json={"name": "List Script", "script_json": {}, "language": "en"},
            headers=auth_headers,
        )

        # List scripts
        response = await client.get("/api/voice/scripts", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(s["name"] == "List Script" for s in data)


async def test_initiate_test_call_service_unavailable(client, auth_headers):
    """Test initiating a test call when voice service is not configured."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/voice/test-call",
            json={"phone_number": "+15551234567"},
            headers=auth_headers,
        )

    # Without call_manager in app.state, it returns 503
    assert response.status_code == 503
    data = response.json()
    assert "not available" in data["detail"].lower()


async def test_get_call_not_found(client, auth_headers):
    """Test getting a call that doesn't exist returns 404."""
    import uuid

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get(
            f"/api/voice/calls/{uuid.uuid4()}", headers=auth_headers
        )

    assert response.status_code == 404


async def test_get_voice_stats_empty(client, auth_headers):
    """Test voice stats endpoint returns valid structure when no calls exist."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/voice/stats", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_calls"] == 0
    assert data["answered_count"] == 0
    assert data["avg_duration_seconds"] == 0.0
    assert data["outcomes"] == {}
    assert data["conversion_rate"] == 0.0


async def test_list_calls_empty(client, auth_headers):
    """Test listing calls when none exist."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/voice/calls", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["calls"] == []
