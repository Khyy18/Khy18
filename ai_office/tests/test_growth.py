"""Тесты для content engine, churn detection, upsell и growth API."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.core.models import (
    ActivityLog,
    Agent,
    Task,
    UpsellEvent,
    WinbackLog,
    Workspace,
)


# ============ Content Engine Tests ============


@pytest.mark.asyncio
async def test_generate_weekly_post(async_session):
    """generate_weekly_post возвращает непустой текст на русском."""
    from ai_office.core.content_engine import generate_weekly_post

    ws = Workspace(
        telegram_chat_id=111, name="TestWS", owner_telegram_id=1
    )
    async_session.add(ws)
    await async_session.commit()

    post = await generate_weekly_post(ws.id, async_session)
    assert len(post) > 0
    assert "дайджест" in post.lower() or "Еженедельный" in post


@pytest.mark.asyncio
async def test_generate_tip_post():
    """generate_tip_post возвращает непустую строку."""
    from ai_office.core.content_engine import generate_tip_post

    tip = await generate_tip_post()
    assert len(tip) > 0
    assert "Совет дня" in tip


@pytest.mark.asyncio
async def test_generate_case_study(async_session):
    """generate_case_study возвращает кейс-стади для существующей задачи."""
    from ai_office.core.content_engine import generate_case_study

    ws = Workspace(
        telegram_chat_id=222, name="CaseWS", owner_telegram_id=2
    )
    async_session.add(ws)
    await async_session.flush()

    agent = Agent(
        name="Sam",
        role="Разработчик",
        system_prompt="test",
        status="idle",
        workspace_id=ws.id,
    )
    async_session.add(agent)
    await async_session.flush()

    task = Task(
        description="Написать API авторизации",
        creator_type="user",
        creator_id="user_1",
        executor_id=agent.id,
        status="completed",
        priority="high",
        workspace_id=ws.id,
        closed_at=datetime.now(timezone.utc),
    )
    async_session.add(task)
    await async_session.commit()

    post = await generate_case_study(task.id, async_session)
    assert "Кейс" in post
    assert "API авторизации" in post
    assert "Sam" in post


# ============ Churn Detection Tests ============


@pytest.mark.asyncio
async def test_calculate_engagement(async_session):
    """calculate_engagement возвращает EngagementScore с валидной оценкой."""
    from ai_office.core.churn_detection import calculate_engagement, EngagementScore

    ws = Workspace(
        telegram_chat_id=333, name="EngageWS", owner_telegram_id=3
    )
    async_session.add(ws)
    await async_session.flush()

    agent = Agent(
        name="Alice",
        role="Ассистент",
        system_prompt="test",
        status="idle",
        workspace_id=ws.id,
    )
    async_session.add(agent)
    await async_session.flush()

    # Add some activity
    for i in range(5):
        log = ActivityLog(
            agent_id=agent.id,
            action_type="message",
            action_description=f"Action {i}",
            workspace_id=ws.id,
        )
        async_session.add(log)
    await async_session.commit()

    score = await calculate_engagement(ws.id, async_session)
    assert isinstance(score, EngagementScore)
    assert score.messages_per_day > 0
    assert score.score >= 0


@pytest.mark.asyncio
async def test_detect_churning_workspaces(async_session):
    """detect_churning_workspaces находит неактивный workspace."""
    from ai_office.core.churn_detection import detect_churning_workspaces

    ws = Workspace(
        telegram_chat_id=444, name="InactiveWS", owner_telegram_id=4
    )
    async_session.add(ws)
    await async_session.flush()

    agent = Agent(
        name="TestAgent",
        role="test",
        system_prompt="test",
        status="idle",
        workspace_id=ws.id,
    )
    async_session.add(agent)
    await async_session.flush()

    # Add old activity (5 days ago)
    old_time = datetime.now(timezone.utc) - timedelta(days=5)
    log = ActivityLog(
        agent_id=agent.id,
        action_type="message",
        action_description="Old action",
        workspace_id=ws.id,
    )
    async_session.add(log)
    await async_session.flush()

    # Manually update timestamp
    log.timestamp = old_time
    await async_session.commit()

    at_risk = await detect_churning_workspaces(async_session)
    assert len(at_risk) >= 1
    found = [r for r in at_risk if r["workspace_id"] == ws.id]
    assert len(found) == 1
    assert found[0]["days_inactive"] >= 4
    assert found[0]["recommended_action"] == "nudge"


@pytest.mark.asyncio
async def test_record_winback_and_can_send(async_session):
    """record_winback записывает лог, can_send_winback блокирует повторы."""
    from ai_office.core.churn_detection import record_winback, can_send_winback

    ws = Workspace(
        telegram_chat_id=555, name="WinbackWS", owner_telegram_id=5
    )
    async_session.add(ws)
    await async_session.commit()

    # Initially can send
    can_send = await can_send_winback(ws.id, "nudge", async_session)
    assert can_send is True

    # Record winback
    await record_winback(ws.id, "nudge", async_session)

    # Now cannot send again
    can_send = await can_send_winback(ws.id, "nudge", async_session)
    assert can_send is False


# ============ Upsell Tests ============


@pytest.mark.asyncio
async def test_check_upsell_triggers_message_limit(async_session):
    """check_upsell_triggers обнаруживает 80% использование лимита сообщений."""
    from ai_office.core.upsell import check_upsell_triggers, TRIGGER_MESSAGE_LIMIT_80

    ws = Workspace(
        telegram_chat_id=666,
        name="UpsellWS",
        owner_telegram_id=6,
    )
    async_session.add(ws)
    await async_session.flush()

    # Set messages used to 85 out of 100 (free tier)
    ws.messages_used_this_month = 85
    await async_session.commit()

    triggers = await check_upsell_triggers(ws.id, async_session)
    assert TRIGGER_MESSAGE_LIMIT_80 in triggers


@pytest.mark.asyncio
async def test_record_upsell_shown_and_stats(async_session):
    """record_upsell_shown записывает событие, get_upsell_stats возвращает статистику."""
    from ai_office.core.upsell import (
        record_upsell_shown,
        get_upsell_stats,
        TRIGGER_MESSAGE_LIMIT_80,
    )

    ws = Workspace(
        telegram_chat_id=777, name="StatsWS", owner_telegram_id=7
    )
    async_session.add(ws)
    await async_session.commit()

    await record_upsell_shown(ws.id, TRIGGER_MESSAGE_LIMIT_80, async_session)
    await record_upsell_shown(ws.id, TRIGGER_MESSAGE_LIMIT_80, async_session)

    stats = await get_upsell_stats(async_session)
    assert stats["total_shown"] == 2
    assert stats["total_converted"] == 0
    assert stats["conversion_rate"] == 0.0
    assert TRIGGER_MESSAGE_LIMIT_80 in stats["by_trigger"]


@pytest.mark.asyncio
async def test_can_show_upsell_rate_limiting(async_session):
    """can_show_upsell ограничивает показ до 1 раз в день."""
    from ai_office.core.upsell import (
        can_show_upsell,
        record_upsell_shown,
        TRIGGER_LOCKED_AGENT,
    )

    ws = Workspace(
        telegram_chat_id=888, name="RateLimitWS", owner_telegram_id=8
    )
    async_session.add(ws)
    await async_session.commit()

    # Initially can show
    can_show = await can_show_upsell(ws.id, TRIGGER_LOCKED_AGENT, async_session)
    assert can_show is True

    # Record shown
    await record_upsell_shown(ws.id, TRIGGER_LOCKED_AGENT, async_session)

    # Now cannot show again today
    can_show = await can_show_upsell(ws.id, TRIGGER_LOCKED_AGENT, async_session)
    assert can_show is False


# ============ API Tests ============


@pytest.mark.asyncio
async def test_api_churn_returns_200(test_client: AsyncClient):
    """GET /api/admin/churn возвращает 200."""
    resp = await test_client.get("/api/admin/churn")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_api_upsell_stats_returns_200(test_client: AsyncClient):
    """GET /api/admin/upsell/stats возвращает 200."""
    resp = await test_client.get("/api/admin/upsell/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_shown" in data
    assert "total_converted" in data
    assert "conversion_rate" in data
    assert "by_trigger" in data
