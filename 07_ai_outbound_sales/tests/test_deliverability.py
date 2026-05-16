"""Tests for channels/email/deliverability_test.py - DeliverabilityTester class.

Verifies test email sending, placement checking, history tracking,
inbox rate calculation, and alert threshold logic.
"""

from unittest.mock import AsyncMock

import pytest

from channels.email.deliverability_test import DeliverabilityTester


@pytest.fixture
def mock_sender() -> AsyncMock:
    """Mock email sender for deliverability tests."""
    sender = AsyncMock()
    sender.send_email = AsyncMock(
        return_value={"success": True, "domain_used": "test.com", "message_id_header": "<test@test.com>"}
    )
    return sender


@pytest.fixture
def tester(mock_sender: AsyncMock) -> DeliverabilityTester:
    """Create a DeliverabilityTester with mock sender."""
    return DeliverabilityTester(email_sender=mock_sender, redis_url="")


async def test_send_test_email_records_result(tester: DeliverabilityTester, mock_sender: AsyncMock):
    """send_test_email sends via the sender and records the result."""
    result = await tester.send_test_email("example.com", "seed@testinbox.com")

    # Verify result structure
    assert "message_id" in result
    assert result["domain"] == "example.com"
    assert "sent_at" in result

    # Verify email sender was called
    mock_sender.send_email.assert_called_once()
    call_kwargs = mock_sender.send_email.call_args[1]
    assert call_kwargs["to"] == "seed@testinbox.com"
    assert "Deliverability Test" in call_kwargs["subject"]

    # Verify stored in history
    history = await tester.get_placement_history("example.com")
    assert len(history) == 1
    assert history[0]["message_id"] == result["message_id"]
    assert history[0]["placement"] == "pending"


async def test_check_placement_returns_correct_status(tester: DeliverabilityTester):
    """check_placement returns the recorded placement after record_placement is called."""
    result = await tester.send_test_email("example.com", "seed@testinbox.com")
    msg_id = result["message_id"]

    # Initially pending
    placement = await tester.check_placement(msg_id)
    assert placement == "pending"

    # Record placement
    await tester.record_placement(msg_id, "inbox")

    # Now should return inbox
    placement = await tester.check_placement(msg_id)
    assert placement == "inbox"


async def test_check_placement_unknown_message(tester: DeliverabilityTester):
    """check_placement returns 'pending' for unknown message IDs."""
    placement = await tester.check_placement("nonexistent-id")
    assert placement == "pending"


async def test_placement_history_tracked(tester: DeliverabilityTester):
    """Placement history is tracked per domain and updated when recorded."""
    # Send multiple test emails
    r1 = await tester.send_test_email("domain-a.com", "seed1@test.com")
    r2 = await tester.send_test_email("domain-a.com", "seed2@test.com")
    r3 = await tester.send_test_email("domain-b.com", "seed3@test.com")

    # Record placements
    await tester.record_placement(r1["message_id"], "inbox")
    await tester.record_placement(r2["message_id"], "spam")
    await tester.record_placement(r3["message_id"], "inbox")

    # Check history for domain-a
    history_a = await tester.get_placement_history("domain-a.com")
    assert len(history_a) == 2
    placements_a = [h["placement"] for h in history_a]
    assert "inbox" in placements_a
    assert "spam" in placements_a

    # Check history for domain-b
    history_b = await tester.get_placement_history("domain-b.com")
    assert len(history_b) == 1
    assert history_b[0]["placement"] == "inbox"

    # Unknown domain returns empty
    history_c = await tester.get_placement_history("unknown.com")
    assert history_c == []


async def test_inbox_rate_calculation(tester: DeliverabilityTester):
    """get_inbox_rate calculates correct percentage based on checked results."""
    # Send 4 test emails
    r1 = await tester.send_test_email("rated.com", "s1@test.com")
    r2 = await tester.send_test_email("rated.com", "s2@test.com")
    r3 = await tester.send_test_email("rated.com", "s3@test.com")
    r4 = await tester.send_test_email("rated.com", "s4@test.com")

    # Record: 3 inbox, 1 spam = 75% inbox rate
    await tester.record_placement(r1["message_id"], "inbox")
    await tester.record_placement(r2["message_id"], "inbox")
    await tester.record_placement(r3["message_id"], "inbox")
    await tester.record_placement(r4["message_id"], "spam")

    rate = await tester.get_inbox_rate("rated.com")
    assert rate == 75.0


async def test_inbox_rate_empty_domain(tester: DeliverabilityTester):
    """get_inbox_rate returns 0.0 for domains with no test history."""
    rate = await tester.get_inbox_rate("empty.com")
    assert rate == 0.0


async def test_inbox_rate_ignores_pending(tester: DeliverabilityTester):
    """get_inbox_rate only counts checked results, ignoring pending."""
    r1 = await tester.send_test_email("partial.com", "s1@test.com")
    r2 = await tester.send_test_email("partial.com", "s2@test.com")

    # Only record one - the other stays pending
    await tester.record_placement(r1["message_id"], "inbox")

    rate = await tester.get_inbox_rate("partial.com")
    assert rate == 100.0  # 1/1 checked = 100%


async def test_alert_fires_below_threshold(tester: DeliverabilityTester):
    """alert_if_degraded returns True when inbox rate is below threshold."""
    # Send 5 test emails, only 2 land in inbox = 40%
    results = []
    for i in range(5):
        r = await tester.send_test_email("degraded.com", f"s{i}@test.com")
        results.append(r)

    await tester.record_placement(results[0]["message_id"], "inbox")
    await tester.record_placement(results[1]["message_id"], "inbox")
    await tester.record_placement(results[2]["message_id"], "spam")
    await tester.record_placement(results[3]["message_id"], "spam")
    await tester.record_placement(results[4]["message_id"], "promotions")

    # 40% inbox rate, threshold is 80% -> alert fires
    alert_needed = await tester.alert_if_degraded("degraded.com", threshold=80.0)
    assert alert_needed is True


async def test_no_alert_above_threshold(tester: DeliverabilityTester):
    """alert_if_degraded returns False when inbox rate is above threshold."""
    # Send 5 test emails, 5 land in inbox = 100%
    results = []
    for i in range(5):
        r = await tester.send_test_email("healthy.com", f"s{i}@test.com")
        results.append(r)

    for r in results:
        await tester.record_placement(r["message_id"], "inbox")

    # 100% inbox rate, threshold is 80% -> no alert
    alert_needed = await tester.alert_if_degraded("healthy.com", threshold=80.0)
    assert alert_needed is False


async def test_no_alert_no_data(tester: DeliverabilityTester):
    """alert_if_degraded returns False when there is no data for the domain."""
    alert_needed = await tester.alert_if_degraded("nodata.com", threshold=80.0)
    assert alert_needed is False
