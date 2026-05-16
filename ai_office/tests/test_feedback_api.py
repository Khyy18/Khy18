"""Тесты для API обратной связи."""

import pytest
from httpx import AsyncClient

from ai_office.core.models import Feedback


@pytest.mark.asyncio
async def test_create_feedback(test_client: AsyncClient, async_session):
    """POST /api/feedback создает запись обратной связи."""
    payload = {
        "user_telegram_id": 123456,
        "agent_name": "alice",
        "rating": 5,
        "is_positive": True,
        "comment": "Отличная работа!",
    }
    response = await test_client.post("/api/feedback", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["agent_name"] == "alice"
    assert data["rating"] == 5
    assert data["is_positive"] is True
    assert data["comment"] == "Отличная работа!"


@pytest.mark.asyncio
async def test_create_feedback_minimal(test_client: AsyncClient, async_session):
    """POST /api/feedback с минимальными данными."""
    payload = {
        "user_telegram_id": 789,
        "agent_name": "sam",
    }
    response = await test_client.post("/api/feedback", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["agent_name"] == "sam"
    assert data["rating"] is None
    assert data["is_positive"] is None


@pytest.mark.asyncio
async def test_get_feedback_stats(test_client: AsyncClient, async_session):
    """GET /api/feedback/stats возвращает статистику по агентам."""
    # Create some feedback entries
    feedbacks = [
        {"user_telegram_id": 1, "agent_name": "alice", "rating": 5, "is_positive": True},
        {"user_telegram_id": 2, "agent_name": "alice", "rating": 4, "is_positive": True},
        {"user_telegram_id": 3, "agent_name": "alice", "rating": 3, "is_positive": False},
        {"user_telegram_id": 4, "agent_name": "sam", "rating": 5, "is_positive": True},
    ]
    for fb in feedbacks:
        await test_client.post("/api/feedback", json=fb)

    response = await test_client.get("/api/feedback/stats")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Find alice stats
    alice_stats = next((s for s in data if s["agent_name"] == "alice"), None)
    assert alice_stats is not None
    assert alice_stats["total_count"] == 3
    assert alice_stats["avg_rating"] == 4.0
    assert alice_stats["positive_percentage"] == pytest.approx(66.7, abs=0.1)

    # Find sam stats
    sam_stats = next((s for s in data if s["agent_name"] == "sam"), None)
    assert sam_stats is not None
    assert sam_stats["total_count"] == 1
    assert sam_stats["positive_percentage"] == 100.0
