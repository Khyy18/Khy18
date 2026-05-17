"""Tests for the Adaptive Throttle module."""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from compliance.adaptive_throttle import AdaptiveThrottle, ThrottleDecision


@pytest.fixture
def mock_settings():
    """Mock settings for adaptive throttle."""
    s = MagicMock()
    s.adaptive_throttle_bounce_threshold = 0.05
    s.adaptive_throttle_cooldown_minutes = 30
    return s


@pytest.fixture
def mock_redis():
    """Mock Redis with dict-based state for throttle tests."""
    redis = AsyncMock()
    store: dict[str, str] = {}

    async def mock_get(key):
        val = store.get(key)
        return val.encode() if val else None

    async def mock_set(key, value, **kwargs):
        store[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(store.get(key, "0"))
        store[key] = str(current + 1)
        return current + 1

    async def mock_expire(key, ttl):
        return True

    async def mock_delete(key):
        store.pop(key, None)
        return 1

    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.incr = AsyncMock(side_effect=mock_incr)
    redis.expire = AsyncMock(side_effect=mock_expire)
    redis.delete = AsyncMock(side_effect=mock_delete)
    redis.close = AsyncMock()
    redis._store = store

    return redis


@pytest.fixture
def throttle(mock_settings, mock_redis):
    """Create AdaptiveThrottle with mocked Redis."""
    with patch("compliance.adaptive_throttle.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_redis
        t = AdaptiveThrottle("redis://localhost:6379/0", mock_settings)
        t._redis = mock_redis
        return t


class TestEmailThrottle:
    """Test email throttle based on bounce rates."""

    async def test_allow_when_no_sends(self, throttle):
        """Should allow when no emails have been sent."""
        decision = await throttle.check_email_throttle("tenant-1")
        assert decision.action == "allow"

    async def test_allow_when_bounce_rate_normal(self, throttle, mock_redis):
        """Should allow when bounce rate is below threshold."""
        mock_redis._store["throttle:email:sent:tenant-1"] = "100"
        mock_redis._store["throttle:email:bounce:tenant-1"] = "2"  # 2%

        decision = await throttle.check_email_throttle("tenant-1")
        assert decision.action == "allow"

    async def test_slow_when_bounce_rate_exceeds_threshold(self, throttle, mock_redis):
        """Should slow when bounce rate exceeds 5%."""
        mock_redis._store["throttle:email:sent:tenant-1"] = "100"
        mock_redis._store["throttle:email:bounce:tenant-1"] = "6"  # 6%

        decision = await throttle.check_email_throttle("tenant-1")
        assert decision.action == "slow"
        assert decision.delay_seconds == 30

    async def test_pause_when_bounce_rate_exceeds_10_percent(self, throttle, mock_redis):
        """Should pause when bounce rate exceeds 10%."""
        mock_redis._store["throttle:email:sent:tenant-1"] = "100"
        mock_redis._store["throttle:email:bounce:tenant-1"] = "11"  # 11%

        decision = await throttle.check_email_throttle("tenant-1")
        assert decision.action == "pause"
        assert decision.delay_seconds == 30 * 60  # cooldown_minutes * 60

    async def test_record_bounce_increments_counter(self, throttle, mock_redis):
        """record_bounce should increment the bounce counter."""
        await throttle.record_bounce("tenant-1")

        assert mock_redis._store["throttle:email:bounce:tenant-1"] == "1"

    async def test_record_email_sent_increments_counter(self, throttle, mock_redis):
        """record_email_sent should increment the sent counter."""
        await throttle.record_email_sent("tenant-1")

        assert mock_redis._store["throttle:email:sent:tenant-1"] == "1"


class TestLinkedInThrottle:
    """Test LinkedIn throttle based on warnings."""

    async def test_allow_when_no_warnings(self, throttle):
        """Should allow when no LinkedIn warnings exist."""
        decision = await throttle.check_linkedin_throttle("tenant-1")
        assert decision.action == "allow"

    async def test_first_warning_pauses_4_hours(self, throttle, mock_redis):
        """First warning should trigger 4h pause."""
        await throttle.record_linkedin_warning("tenant-1")

        decision = await throttle.check_linkedin_throttle("tenant-1")
        assert decision.action == "pause"
        assert decision.delay_seconds > 14000  # ~4h

    async def test_second_warning_pauses_24_hours(self, throttle, mock_redis):
        """Second warning within 24h should trigger 24h pause."""
        await throttle.record_linkedin_warning("tenant-1")
        await throttle.record_linkedin_warning("tenant-1")

        decision = await throttle.check_linkedin_throttle("tenant-1")
        assert decision.action == "pause"
        assert decision.delay_seconds > 80000  # ~24h

    async def test_pause_expires(self, throttle, mock_redis):
        """After pause expires, should allow again."""
        # Set pause in the past
        past_time = str(time.time() - 100)
        mock_redis._store["throttle:linkedin:pause_until:tenant-1"] = past_time

        decision = await throttle.check_linkedin_throttle("tenant-1")
        assert decision.action == "allow"


class TestVoiceThrottle:
    """Test voice throttle based on call answer rates."""

    async def test_allow_with_insufficient_data(self, throttle):
        """Should allow when not enough calls to determine rate."""
        decision = await throttle.check_voice_throttle("tenant-1", hour=10)
        assert decision.action == "allow"
        assert "insufficient_data" in decision.reason

    async def test_allow_with_good_answer_rate(self, throttle, mock_redis):
        """Should allow when answer rate is above 20%."""
        mock_redis._store["throttle:voice:total:tenant-1:10"] = "20"
        mock_redis._store["throttle:voice:answered:tenant-1:10"] = "10"  # 50%

        decision = await throttle.check_voice_throttle("tenant-1", hour=10)
        assert decision.action == "allow"

    async def test_shift_when_answer_rate_low(self, throttle, mock_redis):
        """Should recommend shift when answer rate is below 20%."""
        mock_redis._store["throttle:voice:total:tenant-1:10"] = "20"
        mock_redis._store["throttle:voice:answered:tenant-1:10"] = "2"  # 10%

        decision = await throttle.check_voice_throttle("tenant-1", hour=10)
        assert decision.action == "shift"
        assert decision.recommended_hours is not None
        assert 9 in decision.recommended_hours
        assert 11 in decision.recommended_hours

    async def test_shift_edge_hour_0(self, throttle, mock_redis):
        """At hour 0, recommended should only include hour 1."""
        mock_redis._store["throttle:voice:total:tenant-1:0"] = "10"
        mock_redis._store["throttle:voice:answered:tenant-1:0"] = "1"  # 10%

        decision = await throttle.check_voice_throttle("tenant-1", hour=0)
        assert decision.action == "shift"
        assert decision.recommended_hours == [1]

    async def test_record_call_result_answered(self, throttle, mock_redis):
        """record_call_result should track answered calls."""
        await throttle.record_call_result("tenant-1", hour=14, answered=True)

        assert mock_redis._store["throttle:voice:total:tenant-1:14"] == "1"
        assert mock_redis._store["throttle:voice:answered:tenant-1:14"] == "1"

    async def test_record_call_result_not_answered(self, throttle, mock_redis):
        """record_call_result should track unanswered calls."""
        await throttle.record_call_result("tenant-1", hour=14, answered=False)

        assert mock_redis._store["throttle:voice:total:tenant-1:14"] == "1"
        assert "throttle:voice:answered:tenant-1:14" not in mock_redis._store


class TestThrottleStatus:
    """Test the combined throttle status endpoint."""

    async def test_get_throttle_status(self, throttle, mock_redis):
        """Should return status for all channels."""
        status = await throttle.get_throttle_status("tenant-1")

        assert "email" in status
        assert "linkedin" in status
        assert "voice" in status
        assert status["tenant_id"] == "tenant-1"
        assert status["email"]["action"] == "allow"
        assert status["linkedin"]["action"] == "allow"
        assert status["voice"]["action"] == "allow"
