"""Tests for the Telegram Client Bot and Bot Runner."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models import (
    ApprovalStatus,
    Campaign,
    CampaignStatus,
    Lead,
    LeadStatus,
    PendingApproval,
    Tenant,
)
from integrations.telegram_client_bot import TelegramClientBot
from integrations.telegram_bot_runner import TelegramBotRunner
from tests.conftest import make_campaign, make_lead, make_tenant


@pytest.fixture
def bot(session_factory):
    """Create a TelegramClientBot instance for testing."""
    return TelegramClientBot(bot_token="test-bot-token", session_factory=session_factory)


@pytest.fixture
def runner(bot, session_factory):
    """Create a TelegramBotRunner instance for testing."""
    return TelegramBotRunner(bot=bot, session_factory=session_factory)


# ---------- Test send_message ----------


@pytest.mark.asyncio
async def test_send_message(bot):
    """Test that send_message makes correct API call."""
    with patch("integrations.telegram_client_bot.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {}}
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await bot.send_message("12345", "Hello World")

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/sendMessage" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["chat_id"] == "12345"
        assert payload["text"] == "Hello World"
        assert payload["parse_mode"] == "Markdown"


@pytest.mark.asyncio
async def test_send_message_with_reply_markup(bot):
    """Test that send_message includes reply_markup when provided."""
    with patch("integrations.telegram_client_bot.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {}}
        mock_client.post = AsyncMock(return_value=mock_response)

        markup = {"inline_keyboard": [[{"text": "Click", "callback_data": "test"}]]}
        result = await bot.send_message("12345", "Hello", reply_markup=markup)

        assert result is True
        payload = mock_client.post.call_args[1]["json"]
        assert payload["reply_markup"] == markup


# ---------- Test handle_status ----------


@pytest.mark.asyncio
async def test_handle_status(bot, async_session, session_factory):
    """Test handle_status returns formatted campaign stats."""
    tenant = make_tenant()
    async_session.add(tenant)

    # Add active campaigns
    c1 = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    c2 = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active, name="Campaign 2")
    async_session.add_all([c1, c2])
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_status("chat123", tenant.id)

        mock_send.assert_called_once()
        text = mock_send.call_args[0][1]
        assert "Active Campaigns: 2" in text
        assert "Campaign Status" in text


# ---------- Test handle_hot ----------


@pytest.mark.asyncio
async def test_handle_hot(bot, async_session, session_factory):
    """Test handle_hot returns top 5 hot leads with scores."""
    tenant = make_tenant()
    async_session.add(tenant)

    # Create leads with high scores
    leads = []
    for i in range(7):
        lead = make_lead(
            tenant_id=tenant.id,
            first_name=f"Lead{i}",
            last_name="Test",
            company=f"Company{i}",
            score=90 - i * 3,
        )
        leads.append(lead)
    async_session.add_all(leads)
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_hot("chat123", tenant.id)

        mock_send.assert_called_once()
        text = mock_send.call_args[0][1]
        assert "Hot Leads" in text
        # Should only have 5 leads max
        assert "1." in text
        assert "5." in text


@pytest.mark.asyncio
async def test_handle_hot_no_leads(bot, async_session, session_factory):
    """Test handle_hot with no hot leads found."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_hot("chat123", tenant.id)

        mock_send.assert_called_once()
        text = mock_send.call_args[0][1]
        assert "No hot leads" in text


# ---------- Test handle_pending ----------


@pytest.mark.asyncio
async def test_handle_pending(bot, async_session, session_factory):
    """Test handle_pending shows pending approvals with inline buttons."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    approval = PendingApproval(
        lead_id=lead.id,
        message_id=None,
        proposed_response={"subject": "Test Subject", "action": "send_reply"},
        status=ApprovalStatus.pending,
    )
    async_session.add(approval)
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_pending("chat123", tenant.id)

        mock_send.assert_called_once()
        text = mock_send.call_args[0][1]
        assert "Pending Approval" in text
        assert "Test Subject" in text

        # Check inline buttons
        reply_markup = mock_send.call_args[1]["reply_markup"]
        assert "inline_keyboard" in reply_markup
        buttons = reply_markup["inline_keyboard"][0]
        assert buttons[0]["text"] == "Approve"
        assert "approve:" in buttons[0]["callback_data"]
        assert buttons[1]["text"] == "Reject"
        assert "reject:" in buttons[1]["callback_data"]


# ---------- Test handle_approve ----------


@pytest.mark.asyncio
async def test_handle_approve(bot, async_session, session_factory):
    """Test handle_approve changes approval status to approved."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    approval = PendingApproval(
        lead_id=lead.id,
        message_id=None,
        proposed_response={"subject": "Test", "body": "Body", "action": "send_reply"},
        status=ApprovalStatus.pending,
    )
    async_session.add(approval)
    await async_session.commit()

    approval_id = str(approval.id)
    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        # Patch email sender to avoid send attempts
        with patch("agents.approval_queue.get_email_sender", return_value=None):
            await bot.handle_approve("chat123", tenant.id, approval_id)

    # Verify status changed
    await async_session.refresh(approval)
    assert approval.status == ApprovalStatus.approved


# ---------- Test handle_reject ----------


@pytest.mark.asyncio
async def test_handle_reject(bot, async_session, session_factory):
    """Test handle_reject changes approval status to rejected."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    approval = PendingApproval(
        lead_id=lead.id,
        message_id=None,
        proposed_response={"subject": "Test", "body": "Body", "action": "send_reply"},
        status=ApprovalStatus.pending,
    )
    async_session.add(approval)
    await async_session.commit()

    approval_id = str(approval.id)
    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_reject("chat123", tenant.id, approval_id)

    # Verify status changed
    await async_session.refresh(approval)
    assert approval.status == ApprovalStatus.rejected


# ---------- Test handle_pause and handle_resume ----------


@pytest.mark.asyncio
async def test_handle_pause_resume(bot, async_session, session_factory):
    """Test handle_pause pauses a campaign and handle_resume resumes it."""
    tenant = make_tenant()
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant.id, name="My Campaign", status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.commit()

    bot._session_factory = session_factory

    # Pause
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_pause("chat123", tenant.id, "My Campaign")

        text = mock_send.call_args[0][1]
        assert "paused" in text

    await async_session.refresh(campaign)
    assert campaign.status == CampaignStatus.paused

    # Resume
    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_resume("chat123", tenant.id, "My Campaign")

        text = mock_send.call_args[0][1]
        assert "resumed" in text

    await async_session.refresh(campaign)
    assert campaign.status == CampaignStatus.active


@pytest.mark.asyncio
async def test_handle_pause_not_found(bot, async_session, session_factory):
    """Test handle_pause with non-existent campaign."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await bot.handle_pause("chat123", tenant.id, "Nonexistent")

        text = mock_send.call_args[0][1]
        assert "not found" in text


# ---------- Test resolve_tenant ----------


@pytest.mark.asyncio
async def test_resolve_tenant(runner, async_session, session_factory):
    """Test that _resolve_tenant maps chat_id to tenant_id from settings."""
    tenant = make_tenant(settings={"telegram_client_chat_id": "chat_999"})
    async_session.add(tenant)
    await async_session.commit()

    runner._session_factory = session_factory

    result = await runner._resolve_tenant("chat_999")
    assert result == tenant.id

    # Test caching
    result2 = await runner._resolve_tenant("chat_999")
    assert result2 == tenant.id
    assert "chat_999" in runner._tenant_cache


@pytest.mark.asyncio
async def test_resolve_tenant_not_found(runner, async_session, session_factory):
    """Test _resolve_tenant returns None for unknown chat_id."""
    runner._session_factory = session_factory

    result = await runner._resolve_tenant("unknown_chat")
    assert result is None


# ---------- Test callback routing ----------


@pytest.mark.asyncio
async def test_callback_routing(runner, async_session, session_factory):
    """Test callback_data parsing routes approve/reject correctly."""
    tenant = make_tenant(settings={"telegram_client_chat_id": "100"})
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    approval = PendingApproval(
        lead_id=lead.id,
        message_id=None,
        proposed_response={"subject": "Test", "body": "Body", "action": "send"},
        status=ApprovalStatus.pending,
    )
    async_session.add(approval)
    await async_session.commit()

    runner._session_factory = session_factory
    runner._bot._session_factory = session_factory

    callback_query = {
        "id": "cb_123",
        "data": f"approve:{approval.id}",
        "message": {"chat": {"id": 100}},
    }

    with patch.object(runner._bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch.object(runner._bot, "answer_callback_query", new_callable=AsyncMock) as mock_answer:
            mock_answer.return_value = True
            with patch("agents.approval_queue.get_email_sender", return_value=None):
                await runner._handle_callback(callback_query)

            mock_answer.assert_called_once_with("cb_123", "Approved!")

    # Verify approval was approved
    await async_session.refresh(approval)
    assert approval.status == ApprovalStatus.approved


# ---------- Test notify_positive_reply ----------


@pytest.mark.asyncio
async def test_notify_positive_reply(bot, async_session, session_factory):
    """Test notify_positive_reply sends notification to correct chat_id."""
    tenant = make_tenant(settings={"telegram_client_chat_id": "chat_notify"})
    async_session.add(tenant)
    await async_session.commit()

    bot._session_factory = session_factory

    with patch.object(bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await bot.notify_positive_reply(
            tenant.id,
            {"name": "Jane Smith", "company": "Acme", "email": "jane@acme.com"},
        )

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "chat_notify"
        text = call_args[0][1]
        assert "Positive Reply" in text
        assert "Jane Smith" in text
        assert "Acme" in text


@pytest.mark.asyncio
async def test_notify_positive_reply_no_chat_id(bot, async_session, session_factory):
    """Test notify_positive_reply returns False if no chat_id configured."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.commit()

    bot._session_factory = session_factory

    result = await bot.notify_positive_reply(
        tenant.id,
        {"name": "Jane", "company": "Acme", "email": "jane@acme.com"},
    )
    assert result is False


# ---------- Test command routing ----------


@pytest.mark.asyncio
async def test_command_routing_status(runner, async_session, session_factory):
    """Test that /status command is routed correctly."""
    tenant = make_tenant(settings={"telegram_client_chat_id": "chat_cmd"})
    async_session.add(tenant)
    await async_session.commit()

    runner._session_factory = session_factory
    runner._bot._session_factory = session_factory

    message = {
        "chat": {"id": "chat_cmd"},
        "text": "/status",
    }

    with patch.object(runner._bot, "handle_status", new_callable=AsyncMock) as mock_handler:
        with patch.object(runner._bot, "send_message", new_callable=AsyncMock):
            await runner._handle_command(message)
            mock_handler.assert_called_once_with("chat_cmd", tenant.id)


@pytest.mark.asyncio
async def test_command_routing_pause_with_args(runner, async_session, session_factory):
    """Test that /pause command passes campaign name as argument."""
    tenant = make_tenant(settings={"telegram_client_chat_id": "chat_cmd2"})
    async_session.add(tenant)
    await async_session.commit()

    runner._session_factory = session_factory
    runner._bot._session_factory = session_factory

    message = {
        "chat": {"id": "chat_cmd2"},
        "text": "/pause My Campaign",
    }

    with patch.object(runner._bot, "handle_pause", new_callable=AsyncMock) as mock_handler:
        with patch.object(runner._bot, "send_message", new_callable=AsyncMock):
            await runner._handle_command(message)
            mock_handler.assert_called_once_with("chat_cmd2", tenant.id, "My Campaign")
