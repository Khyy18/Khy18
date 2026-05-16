"""Тесты подсистемы подписок и публичного API."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.core.models import ActivityLog, Agent, Workspace
from ai_office.core.subscription import (
    TIERS,
    check_access,
    check_message_limit,
    get_subscription_status,
    increment_message_count,
    reset_monthly_counts,
)


@pytest_asyncio.fixture
async def workspace_free(async_session):
    """Workspace с бесплатной подпиской."""
    ws = Workspace(
        telegram_chat_id=100001,
        name="Test Free Workspace",
        owner_telegram_id=200001,
        subscription_tier="free",
        messages_used_this_month=0,
        is_public=False,
    )
    async_session.add(ws)
    await async_session.commit()
    await async_session.refresh(ws)
    return ws


@pytest_asyncio.fixture
async def workspace_pro(async_session):
    """Workspace с pro подпиской."""
    ws = Workspace(
        telegram_chat_id=100002,
        name="Test Pro Workspace",
        owner_telegram_id=200002,
        subscription_tier="pro",
        messages_used_this_month=0,
        is_public=False,
    )
    async_session.add(ws)
    await async_session.commit()
    await async_session.refresh(ws)
    return ws


@pytest_asyncio.fixture
async def workspace_public(async_session):
    """Публичный workspace."""
    ws = Workspace(
        telegram_chat_id=100003,
        name="Public Demo Workspace",
        owner_telegram_id=200003,
        subscription_tier="free",
        messages_used_this_month=0,
        is_public=True,
    )
    async_session.add(ws)
    await async_session.commit()
    await async_session.refresh(ws)
    return ws


# --- Tests for check_access ---


@pytest.mark.asyncio
async def test_check_access_free_tier_alice_allowed(async_session, workspace_free):
    """Alice доступна на бесплатном тарифе."""
    result = await check_access(workspace_free.id, "alice", async_session)
    assert result["allowed"] is True
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_check_access_free_tier_sam_allowed(async_session, workspace_free):
    """Sam доступен на бесплатном тарифе."""
    result = await check_access(workspace_free.id, "sam", async_session)
    assert result["allowed"] is True
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_check_access_free_tier_max_blocked(async_session, workspace_free):
    """Max не доступен на бесплатном тарифе."""
    result = await check_access(workspace_free.id, "max", async_session)
    assert result["allowed"] is False
    assert "max" in result["reason"].lower()


@pytest.mark.asyncio
async def test_check_access_free_tier_eva_blocked(async_session, workspace_free):
    """Eva не доступна на бесплатном тарифе."""
    result = await check_access(workspace_free.id, "eva", async_session)
    assert result["allowed"] is False


@pytest.mark.asyncio
async def test_check_access_pro_tier_all_allowed(async_session, workspace_pro):
    """Все агенты доступны на pro тарифе."""
    for agent_name in TIERS["pro"]["allowed_agents"]:
        result = await check_access(workspace_pro.id, agent_name, async_session)
        assert result["allowed"] is True, f"{agent_name} should be allowed on pro"
        assert result["reason"] is None


@pytest.mark.asyncio
async def test_check_access_nonexistent_workspace(async_session):
    """Несуществующий workspace возвращает False."""
    result = await check_access(99999, "alice", async_session)
    assert result["allowed"] is False
    assert "not found" in result["reason"].lower()


# --- Tests for check_message_limit ---


@pytest.mark.asyncio
async def test_check_message_limit_fresh_workspace(async_session, workspace_free):
    """Свежий workspace имеет 100 оставшихся сообщений."""
    result = await check_message_limit(workspace_free.id, async_session)
    assert result["remaining"] == 100
    assert result["limit"] == 100
    assert result["used"] == 0


@pytest.mark.asyncio
async def test_check_message_limit_after_usage(async_session, workspace_free):
    """После использования сообщений лимит уменьшается."""
    workspace_free.messages_used_this_month = 30
    await async_session.commit()

    result = await check_message_limit(workspace_free.id, async_session)
    assert result["remaining"] == 70
    assert result["limit"] == 100
    assert result["used"] == 30


@pytest.mark.asyncio
async def test_check_message_limit_pro_unlimited(async_session, workspace_pro):
    """Pro тариф имеет unlimited сообщения."""
    result = await check_message_limit(workspace_pro.id, async_session)
    assert result["remaining"] is None
    assert result["limit"] is None
    assert result["used"] == 0


# --- Tests for increment_message_count ---


@pytest.mark.asyncio
async def test_increment_message_count(async_session, workspace_free):
    """Инкремент счётчика сообщений."""
    assert workspace_free.messages_used_this_month == 0

    await increment_message_count(workspace_free.id, async_session)
    await async_session.refresh(workspace_free)
    assert workspace_free.messages_used_this_month == 1

    await increment_message_count(workspace_free.id, async_session)
    await async_session.refresh(workspace_free)
    assert workspace_free.messages_used_this_month == 2


# --- Tests for reset_monthly_counts ---


@pytest.mark.asyncio
async def test_reset_monthly_counts(async_session, workspace_free):
    """Сброс ежемесячных счётчиков."""
    workspace_free.messages_used_this_month = 50
    await async_session.commit()

    await reset_monthly_counts(async_session)
    await async_session.refresh(workspace_free)
    assert workspace_free.messages_used_this_month == 0


# --- Tests for get_subscription_status ---


@pytest.mark.asyncio
async def test_get_subscription_status_free(async_session, workspace_free):
    """Статус бесплатной подписки."""
    status = await get_subscription_status(workspace_free.id, async_session)
    assert status["tier"] == "free"
    assert status["messages_remaining"] == 100
    assert status["messages_limit"] == 100
    assert status["messages_used"] == 0
    assert "alice" in status["agents_available"]
    assert "sam" in status["agents_available"]
    assert "max" not in status["agents_available"]


# --- Tests for Public API endpoints ---


@pytest.mark.asyncio
async def test_public_agents_public_workspace(test_client: AsyncClient, async_session, workspace_public):
    """GET /api/public/{id}/agents для публичного workspace возвращает 200."""
    # Add some agents
    alice = Agent(name="Alice", role="Ассистент", system_prompt="test", status="idle")
    sam = Agent(name="Sam", role="Разработчик", system_prompt="test", status="busy")
    async_session.add_all([alice, sam])
    await async_session.commit()

    resp = await test_client.get(f"/api/public/{workspace_public.id}/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [a["name"] for a in data]
    assert "Alice" in names
    assert "Sam" in names


@pytest.mark.asyncio
async def test_public_agents_non_public_workspace(test_client: AsyncClient, async_session, workspace_free):
    """GET /api/public/{id}/agents для непубличного workspace возвращает 404."""
    resp = await test_client.get(f"/api/public/{workspace_free.id}/agents")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workspace not found or not public"


@pytest.mark.asyncio
async def test_public_agents_nonexistent_workspace(test_client: AsyncClient):
    """GET /api/public/99999/agents для несуществующего workspace возвращает 404."""
    resp = await test_client.get("/api/public/99999/agents")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workspace not found or not public"


@pytest.mark.asyncio
async def test_public_activity_public_workspace(test_client: AsyncClient, async_session, workspace_public):
    """GET /api/public/{id}/activity для публичного workspace возвращает 200."""
    agent = Agent(name="Alice", role="Ассистент", system_prompt="test", status="idle")
    async_session.add(agent)
    await async_session.flush()

    log = ActivityLog(
        agent_id=agent.id,
        action_type="task_completed",
        action_description="Выполнена задача: Тест",
        workspace_id=workspace_public.id,
    )
    async_session.add(log)
    await async_session.commit()

    resp = await test_client.get(f"/api/public/{workspace_public.id}/activity")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "Alice"
    assert data[0]["action_type"] == "task_completed"


@pytest.mark.asyncio
async def test_public_activity_non_public_workspace(test_client: AsyncClient, async_session, workspace_free):
    """GET /api/public/{id}/activity для непубличного workspace возвращает 404."""
    resp = await test_client.get(f"/api/public/{workspace_free.id}/activity")
    assert resp.status_code == 404


# --- Tests for Subscription API endpoint ---


@pytest.mark.asyncio
async def test_subscription_status_api(test_client: AsyncClient, async_session, workspace_free):
    """GET /api/subscription/status возвращает статус подписки."""
    resp = await test_client.get("/api/subscription/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["messages_used"] == 0
    assert "alice" in data["agents_available"]


@pytest.mark.asyncio
async def test_subscription_upgrade_api(test_client: AsyncClient, async_session, workspace_free):
    """POST /api/subscription/upgrade повышает тарифный план."""
    resp = await test_client.post(
        "/api/subscription/upgrade",
        json={"tier": "pro"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "pro"
    assert data["messages_limit"] is None
    assert "max" in data["agents_available"]


@pytest.mark.asyncio
async def test_subscription_upgrade_invalid_tier(test_client: AsyncClient, async_session, workspace_free):
    """POST /api/subscription/upgrade с неизвестным тарифом возвращает 400."""
    resp = await test_client.post(
        "/api/subscription/upgrade",
        json={"tier": "enterprise"},
    )
    assert resp.status_code == 400
