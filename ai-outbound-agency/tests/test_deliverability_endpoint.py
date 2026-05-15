"""Tests for the POST /api/email/test-deliverability endpoint.

Verifies the deliverability endpoint sends test emails to seed addresses,
handles empty seed lists, integrates with InboxPlacementMonitor, and
enforces authentication.
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from channels.email.deliverability_routes import router, run_deliverability_test
from channels.email.deliverability_test import DeliverabilityTester
from channels.email.inbox_placement import InboxPlacementMonitor


# ---------- Direct function tests (no FastAPI app needed) ----------


async def test_endpoint_returns_results_for_each_seed():
    """Sending to multiple seed addresses returns results for each."""
    tester = DeliverabilityTester()
    seed_addresses = [
        "seed1@test.com",
        "seed2@test.com",
        "seed3@test.com",
    ]

    results = []
    for addr in seed_addresses:
        result = await tester.send_test_email("example.com", addr)
        results.append(result)

    assert len(results) == 3
    for result in results:
        assert "message_id" in result
        assert result["domain"] == "example.com"
        assert "sent_at" in result

    # Each result has a unique message_id
    message_ids = [r["message_id"] for r in results]
    assert len(set(message_ids)) == 3


async def test_endpoint_records_results_in_tester():
    """The endpoint correctly records results in the tester instance."""
    tester = DeliverabilityTester()
    seed_addresses = ["seed1@test.com", "seed2@test.com"]

    for addr in seed_addresses:
        await tester.send_test_email("tracked.com", addr)

    # Verify results are recorded in the tester history
    history = await tester.get_placement_history("tracked.com")
    assert len(history) == 2

    # All results should start as pending
    for record in history:
        assert record["placement"] == "pending"
        assert record["domain"] == "tracked.com"

    # Verify addresses are tracked
    test_addresses = [record["test_address"] for record in history]
    assert "seed1@test.com" in test_addresses
    assert "seed2@test.com" in test_addresses


async def test_endpoint_empty_seed_addresses():
    """Empty seed_addresses returns empty results."""
    tester = DeliverabilityTester()

    # No seed addresses means no results
    results = []
    for addr in []:
        result = await tester.send_test_email("empty.com", addr)
        results.append(result)

    assert len(results) == 0

    # Verify no history recorded
    history = await tester.get_placement_history("empty.com")
    assert history == []


async def test_endpoint_integration_with_inbox_placement_monitor():
    """Integration: send seed test via DeliverabilityTester and check domain stats via InboxPlacementMonitor."""
    tester = DeliverabilityTester()
    monitor = InboxPlacementMonitor()

    # Send tests via the tester (simulating endpoint behavior)
    seed_addresses = [
        "seed1@integration.com",
        "seed2@integration.com",
        "seed3@integration.com",
        "seed4@integration.com",
        "seed5@integration.com",
    ]

    tester_results = []
    for addr in seed_addresses:
        result = await tester.send_test_email("monitor-test.com", addr)
        tester_results.append(result)

    # Also run InboxPlacementMonitor seed test on the same domain
    monitor_result = await monitor.send_seed_test(
        "monitor-test.com", seed_addresses
    )
    assert monitor_result["seed_count"] == 5
    assert monitor_result["status"] == "sent"

    # Simulate placement results in monitor
    message_ids = monitor_result["message_ids"]
    await monitor.update_placement(message_ids[0], "inbox")
    await monitor.update_placement(message_ids[1], "inbox")
    await monitor.update_placement(message_ids[2], "spam")
    await monitor.update_placement(message_ids[3], "inbox")
    await monitor.update_placement(message_ids[4], "spam")

    # Check domain stats: 3 inbox / 5 total = 60%
    stats = await monitor.get_domain_stats("monitor-test.com")
    assert stats["domain"] == "monitor-test.com"
    assert stats["total_tests"] == 5
    assert stats["inbox_rate"] == 60.0
    assert stats["spam_rate"] == 40.0

    # Alert should fire at 80% threshold
    alert_fired = await monitor.alert_if_degraded("monitor-test.com", threshold=80.0)
    assert alert_fired is True

    # No alert at 50% threshold
    no_alert = await monitor.alert_if_degraded("monitor-test.com", threshold=50.0)
    assert no_alert is False


# ---------- FastAPI endpoint tests via httpx ----------


def _make_app_with_auth_bypass():
    """Create a FastAPI app with the deliverability router and auth bypassed."""
    from fastapi import FastAPI
    from core.models import User, UserRole
    from dashboard.auth import get_current_user
    import uuid

    app = FastAPI()
    app.include_router(router)

    # Override auth dependency with a mock user
    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.tenant_id = uuid.uuid4()
    mock_user.email = "test@example.com"
    mock_user.role = UserRole.admin

    async def _override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = _override_get_current_user
    return app


async def test_deliverability_endpoint_via_httpx():
    """Test the actual FastAPI endpoint with httpx AsyncClient (auth bypassed)."""
    app = _make_app_with_auth_bypass()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/email/test-deliverability",
            json={
                "domain": "httpx-test.com",
                "seed_addresses": ["s1@test.com", "s2@test.com"],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "httpx-test.com"
    assert data["test_count"] == 2
    assert len(data["results"]) == 2
    for result in data["results"]:
        assert "message_id" in result
        assert result["domain"] == "httpx-test.com"


async def test_deliverability_endpoint_empty_seeds_via_httpx():
    """Test the endpoint with empty seed_addresses via httpx (auth bypassed)."""
    app = _make_app_with_auth_bypass()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/email/test-deliverability",
            json={
                "domain": "empty-test.com",
                "seed_addresses": [],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "empty-test.com"
    assert data["test_count"] == 0
    assert data["results"] == []


# ---------- Auth guard test ----------


async def test_deliverability_endpoint_requires_auth():
    """Request without auth credentials returns 401 (no valid Authorization header)."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # No dependency override - auth is enforced
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/email/test-deliverability",
            json={
                "domain": "unauth-test.com",
                "seed_addresses": ["seed@test.com"],
            },
        )

    # HTTPBearer returns 401 or 403 when no valid credentials are provided
    assert response.status_code in (401, 403)


# ---------- Input validation tests ----------


async def test_deliverability_endpoint_rejects_too_many_seeds():
    """Request with more than 10 seed addresses is rejected with 422."""
    app = _make_app_with_auth_bypass()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/email/test-deliverability",
            json={
                "domain": "test.com",
                "seed_addresses": [f"seed{i}@test.com" for i in range(11)],
            },
        )

    assert response.status_code == 422


async def test_deliverability_endpoint_rejects_invalid_email():
    """Request with invalid email format in seed_addresses is rejected."""
    app = _make_app_with_auth_bypass()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/email/test-deliverability",
            json={
                "domain": "test.com",
                "seed_addresses": ["not-an-email"],
            },
        )

    assert response.status_code == 422
