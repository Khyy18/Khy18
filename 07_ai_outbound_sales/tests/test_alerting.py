"""Tests for the AlertingEngine - alert condition detection, cooldown, and dispatch."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.alerting import AlertingEngine


@pytest.fixture
def alerting_engine(mock_redis, session_factory, mock_settings):
    """Create an AlertingEngine instance with test dependencies."""
    return AlertingEngine(
        settings=mock_settings,
        session_factory=session_factory,
        redis=mock_redis,
    )


@pytest.fixture
def _seed_bounce_data(async_session):
    """Helper to seed message and event data for bounce rate tests."""

    async def _seed(total_sent: int, bounces: int):
        from core.models import (
            Campaign,
            CampaignStatus,
            Event,
            EventType,
            Lead,
            LeadStatus,
            Message,
            MessageStatus,
            Tenant,
        )

        tenant = Tenant(
            id=uuid.uuid4(),
            name="Test Corp",
            domain="test.com",
            settings={},
        )
        async_session.add(tenant)

        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Test Campaign",
            icp_filter={},
            status=CampaignStatus.active,
        )
        async_session.add(campaign)

        lead = Lead(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="lead@example.com",
            first_name="Test",
            last_name="Lead",
            company="Acme",
            title="VP",
            status=LeadStatus.new,
            enrichment_data={},
        )
        async_session.add(lead)
        await async_session.flush()

        now = datetime.now(timezone.utc)
        for i in range(total_sent):
            msg = Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                campaign_id=campaign.id,
                channel="email",
                direction="outbound",
                content=f"Message {i}",
                subject=f"Subject {i}",
                status=MessageStatus.sent,
                sent_at=now - timedelta(minutes=30),
            )
            async_session.add(msg)
            await async_session.flush()

            if i < bounces:
                event = Event(
                    id=uuid.uuid4(),
                    message_id=msg.id,
                    event_type=EventType.bounce,
                    occurred_at=now - timedelta(minutes=20),
                )
                async_session.add(event)

        await async_session.commit()

    return _seed


async def test_bounce_rate_alert_triggers(alerting_engine, async_session, _seed_bounce_data):
    """Alert triggers when bounce rate exceeds 5%."""
    # 10 messages sent, 2 bounces = 20% bounce rate
    await _seed_bounce_data(10, 2)

    is_triggered, value, message = await alerting_engine._check_bounce_rate(5.0)

    assert is_triggered is True
    assert value == 20.0
    assert "20.0%" in message


async def test_bounce_rate_alert_below_threshold(alerting_engine, async_session, _seed_bounce_data):
    """Alert does not trigger when bounce rate is below threshold."""
    # 100 messages sent, 2 bounces = 2% bounce rate
    await _seed_bounce_data(100, 2)

    is_triggered, value, message = await alerting_engine._check_bounce_rate(5.0)

    assert is_triggered is False
    assert value == 2.0


async def test_cooldown_prevents_duplicate_alert(alerting_engine, mock_redis):
    """Cooldown prevents duplicate alerts from being sent."""
    condition_name = "bounce_rate_high"

    # Initially no cooldown
    assert await alerting_engine.is_in_cooldown(condition_name) is False

    # Set cooldown
    await alerting_engine.set_cooldown(condition_name)

    # Now should be in cooldown
    assert await alerting_engine.is_in_cooldown(condition_name) is True


async def test_cooldown_expires_allows_new_alert(alerting_engine, mock_redis):
    """After cooldown expires (simulated), new alerts can fire."""
    condition_name = "disk_usage_high"

    # Set cooldown
    await alerting_engine.set_cooldown(condition_name)
    assert await alerting_engine.is_in_cooldown(condition_name) is True

    # Simulate cooldown expiry by removing the key from mock store
    key = f"alert_cooldown:{condition_name}"
    mock_redis._store.pop(key, None)

    # Now should not be in cooldown
    assert await alerting_engine.is_in_cooldown(condition_name) is False


async def test_disk_usage_alert(alerting_engine):
    """Disk usage alert checks system disk usage."""
    # Disk usage is system-dependent; just verify the method runs without error
    # and returns a valid tuple
    is_triggered, value, message = await alerting_engine._check_disk_usage(85.0)

    assert isinstance(is_triggered, bool)
    assert isinstance(value, float)
    assert value >= 0.0
    assert "Disk usage" in message


async def test_send_alert_telegram(alerting_engine, mock_settings):
    """Test sending alert via Telegram channel."""
    mock_settings.telegram_bot_token = "test-bot-token"
    mock_settings.telegram_chat_id = "test-chat-id"

    with patch(
        "integrations.notifications.send_telegram_notification",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_telegram:
        result = await alerting_engine.send_alert(
            "bounce_rate_high",
            "telegram",
            "Bounce rate is 15%",
        )

        assert result is True
        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args
        assert call_args[0][0] == "test-bot-token"
        assert call_args[0][1] == "test-chat-id"
        assert "bounce_rate_high" in call_args[0][2]


async def test_send_alert_slack(alerting_engine, mock_settings):
    """Test sending alert via Slack channel."""
    mock_settings.slack_webhook_url = "https://hooks.slack.com/test"

    with patch(
        "integrations.notifications.send_slack_notification",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_slack:
        result = await alerting_engine.send_alert(
            "llm_error_rate_high",
            "slack",
            "LLM error rate is 15%",
        )

        assert result is True
        mock_slack.assert_called_once()
        call_args = mock_slack.call_args
        assert call_args[0][0] == "https://hooks.slack.com/test"


async def test_check_all_conditions(alerting_engine, mock_redis):
    """check_all_conditions evaluates all conditions and returns triggered list."""
    # Mock all individual check methods to return controlled results
    with patch.object(
        alerting_engine, "_check_bounce_rate", return_value=(False, 2.0, "OK")
    ), patch.object(
        alerting_engine, "_check_llm_error_rate", return_value=(True, 15.0, "LLM errors high")
    ), patch.object(
        alerting_engine, "_check_no_sends_business_hours", return_value=(False, 5.0, "OK")
    ), patch.object(
        alerting_engine, "_check_disk_usage", return_value=(False, 50.0, "OK")
    ), patch.object(
        alerting_engine, "_check_memory_usage", return_value=(False, 60.0, "OK")
    ), patch.object(
        alerting_engine, "_check_linkedin_failures", return_value=(False, 1.0, "OK")
    ), patch.object(
        alerting_engine, "_check_mrr_drop", return_value=(False, 2.0, "OK")
    ), patch.object(
        alerting_engine, "_check_db_pool_exhaustion", return_value=(False, 30.0, "OK")
    ), patch.object(
        alerting_engine, "send_alert", return_value=True
    ):
        triggered = await alerting_engine.check_all_conditions()

        # Only llm_error_rate_high should trigger
        assert len(triggered) == 1
        assert triggered[0]["name"] == "llm_error_rate_high"
        assert triggered[0]["value"] == 15.0
