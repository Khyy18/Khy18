"""Tests for the AsyncEmailSender."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from channels.email.sender import AsyncEmailSender


@pytest.fixture
def smtp_accounts():
    return [
        {
            "domain": "domain1.com",
            "host": "smtp.domain1.com",
            "port": 465,
            "user": "sender",
            "password": "pass1",
            "daily_limit": 50,
        },
        {
            "domain": "domain2.com",
            "host": "smtp.domain2.com",
            "port": 465,
            "user": "sender",
            "password": "pass2",
            "daily_limit": 50,
        },
    ]


@pytest.fixture
def email_sender(smtp_accounts, mock_redis):
    """Create sender with mocked Redis."""
    sender = AsyncEmailSender.__new__(AsyncEmailSender)
    sender._accounts = smtp_accounts
    sender._redis = mock_redis
    sender._current_index = 0
    sender._reputation_tracker = None
    return sender


async def test_pick_account_rotates_domains(email_sender, mock_redis):
    """Test domain rotation picks next available domain."""
    # Both domains have 0 sends
    account1 = await email_sender._pick_account()
    assert account1["domain"] == "domain1.com"

    account2 = await email_sender._pick_account()
    assert account2["domain"] == "domain2.com"

    account3 = await email_sender._pick_account()
    assert account3["domain"] == "domain1.com"


async def test_pick_account_skips_domains_at_limit(email_sender, mock_redis):
    """Test daily limit enforcement skips domains at limit."""
    from datetime import date

    # Set domain1 at daily limit
    key = f"email:sends:domain1.com:{date.today().isoformat()}"
    mock_redis._store[key] = "50"
    # Reset index to start from domain1
    email_sender._current_index = 0

    account = await email_sender._pick_account()

    # Should skip domain1 (at limit 50) and pick domain2
    assert account["domain"] == "domain2.com"


async def test_pick_account_returns_none_all_at_limit(email_sender, mock_redis):
    """Test _pick_account returns None when all domains hit daily limit."""
    from datetime import date

    # Set both domains at daily limit
    mock_redis._store[f"email:sends:domain1.com:{date.today().isoformat()}"] = "50"
    mock_redis._store[f"email:sends:domain2.com:{date.today().isoformat()}"] = "50"

    account = await email_sender._pick_account()
    assert account is None


def test_inject_tracking_adds_pixel(email_sender):
    """Test tracking pixel injection adds img tag."""
    html = "<p>Hello world</p>"
    pixel_url = "http://track.example.com/pixel/123"

    result = email_sender._inject_tracking(html, tracking_pixel_url=pixel_url)

    assert pixel_url in result
    assert '<img src="http://track.example.com/pixel/123"' in result
    assert 'width="1" height="1"' in result


def test_inject_tracking_rewrites_links(email_sender):
    """Test tracked links are rewritten."""
    html = '<a href="https://example.com/page">Click here</a>'
    tracked_links = {"https://example.com/page": "https://track.example.com/click/abc"}

    result = email_sender._inject_tracking(html, tracked_links=tracked_links)

    assert "https://track.example.com/click/abc" in result
    assert "https://example.com/page" not in result


async def test_send_email_success(email_sender, mock_redis):
    """Test successful email send."""
    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)
        mock_smtp.login = AsyncMock()
        mock_smtp.send_message = AsyncMock()
        mock_smtp_class.return_value = mock_smtp

        result = await email_sender.send_email(
            to="recipient@example.com",
            subject="Test Subject",
            html_body="<p>Hello</p>",
            message_id="msg-123",
        )

    assert result["success"] is True
    assert result["domain_used"] is not None


async def test_send_email_no_available_domain(email_sender, mock_redis):
    """Test send_email returns failure when no domains available."""
    from datetime import date

    mock_redis._store[f"email:sends:domain1.com:{date.today().isoformat()}"] = "50"
    mock_redis._store[f"email:sends:domain2.com:{date.today().isoformat()}"] = "50"

    result = await email_sender.send_email(
        to="recipient@example.com",
        subject="Test",
        html_body="<p>Test</p>",
        message_id="msg-456",
    )

    assert result["success"] is False
    assert result["domain_used"] is None


async def test_send_email_retry_on_transient_error(email_sender, mock_redis):
    """Test retry logic on transient SMTP errors."""
    import aiosmtplib

    with patch("aiosmtplib.SMTP") as mock_smtp_class:
        mock_smtp = AsyncMock()
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)
        mock_smtp.login = AsyncMock()
        # First attempt fails with transient error, second succeeds
        mock_smtp.send_message = AsyncMock(
            side_effect=[
                aiosmtplib.SMTPResponseException(421, "Temporary failure"),
                None,
            ]
        )
        mock_smtp_class.return_value = mock_smtp

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await email_sender.send_email(
                to="recipient@example.com",
                subject="Test",
                html_body="<p>Test</p>",
                message_id="msg-retry",
            )

    assert result["success"] is True
