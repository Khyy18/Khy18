"""Tests for ApprovalQueue - create, approve sends email, reject."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from core.models import ApprovalStatus, Lead, LeadStatus, PendingApproval
from agents.approval_queue import ApprovalQueue, set_email_sender, get_email_sender
from tests.conftest import make_lead, make_tenant


@pytest.fixture
def mock_sender():
    """Create a mock email sender."""
    sender = AsyncMock()
    sender.send_email = AsyncMock(
        return_value={"success": True, "domain_used": "example.com", "message_id_header": "<test@example.com>"}
    )
    return sender


@pytest.fixture(autouse=True)
def setup_email_sender(mock_sender):
    """Set and clean up the module-level email sender for each test."""
    set_email_sender(mock_sender)
    yield
    set_email_sender(None)


@pytest.mark.asyncio
async def test_create_approval(async_session):
    """Test that create_approval creates a pending approval record."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Follow up", "body": "Hello!", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    assert approval.id is not None
    assert approval.lead_id == lead.id
    assert approval.status == ApprovalStatus.pending
    assert approval.proposed_response == proposed_response


@pytest.mark.asyncio
async def test_approve_sends_email(async_session, mock_sender):
    """Test that approving an approval actually sends the email."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id, email="lead@example.com")
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Follow up", "body": "<p>Hello!</p>", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    result = await ApprovalQueue.approve(
        session=async_session,
        approval_id=approval.id,
        reviewer_notes="Looks good",
    )

    assert result.status == ApprovalStatus.approved
    assert result.reviewer_notes == "Looks good"
    assert result.reviewed_at is not None

    # Verify email was sent
    mock_sender.send_email.assert_awaited_once_with(
        to="lead@example.com",
        subject="Follow up",
        html_body="<p>Hello!</p>",
        message_id=str(approval.id),
    )


@pytest.mark.asyncio
async def test_reject_does_not_send_email(async_session, mock_sender):
    """Test that rejecting an approval does not send an email."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Follow up", "body": "Hello!", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    result = await ApprovalQueue.reject(
        session=async_session,
        approval_id=approval.id,
        reviewer_notes="Not appropriate",
    )

    assert result.status == ApprovalStatus.rejected
    assert result.reviewer_notes == "Not appropriate"
    mock_sender.send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_and_send_sends_edited_email(async_session, mock_sender):
    """Test that edit_and_send updates the response and sends it."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id, email="edited@example.com")
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Old subject", "body": "Old body", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    edited_response = {"subject": "New subject", "body": "<p>New body</p>", "action": "send_reply"}

    result = await ApprovalQueue.edit_and_send(
        session=async_session,
        approval_id=approval.id,
        edited_response=edited_response,
    )

    assert result.status == ApprovalStatus.approved
    assert result.proposed_response == edited_response

    # Verify email was sent with edited content
    mock_sender.send_email.assert_awaited_once_with(
        to="edited@example.com",
        subject="New subject",
        html_body="<p>New body</p>",
        message_id=str(approval.id),
    )


@pytest.mark.asyncio
async def test_approve_without_sender_logs_warning(async_session):
    """Test that approve works but logs warning when no email sender is configured."""
    set_email_sender(None)

    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Test", "body": "Test", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    # Should not raise even without email sender
    result = await ApprovalQueue.approve(
        session=async_session,
        approval_id=approval.id,
    )

    assert result.status == ApprovalStatus.approved


@pytest.mark.asyncio
async def test_approve_already_approved_raises(async_session, mock_sender):
    """Test that approving an already approved item raises ValueError."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    proposed_response = {"subject": "Test", "body": "Test", "action": "send_reply"}

    approval = await ApprovalQueue.create_approval(
        session=async_session,
        lead_id=lead.id,
        message_id=None,
        proposed_response=proposed_response,
    )

    await ApprovalQueue.approve(session=async_session, approval_id=approval.id)

    with pytest.raises(ValueError, match="not in pending status"):
        await ApprovalQueue.approve(session=async_session, approval_id=approval.id)
