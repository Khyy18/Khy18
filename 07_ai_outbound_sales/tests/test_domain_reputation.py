"""Tests for the DomainReputationTracker class."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.email.domain_reputation import DomainReputationTracker


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client using AsyncMock with dict-based state."""
    redis = AsyncMock()
    store: dict[str, str] = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, **kwargs):
        store[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(store.get(key, "0"))
        store[key] = str(current + 1)
        return current + 1

    def _make_pipeline():
        pipe = MagicMock()
        pipe.incr = MagicMock(return_value=pipe)
        pipe.expire = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[1, True])
        return pipe

    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.incr = AsyncMock(side_effect=mock_incr)
    redis.expire = AsyncMock(return_value=True)
    redis.pipeline = MagicMock(return_value=_make_pipeline())
    redis.close = AsyncMock()
    redis._store = store

    return redis


@pytest.fixture
def tracker(mock_redis: AsyncMock) -> DomainReputationTracker:
    """Return a DomainReputationTracker with mocked Redis."""
    t = DomainReputationTracker.__new__(DomainReputationTracker)
    t._redis = mock_redis
    return t


class TestDomainReputationTracker:
    """Tests for DomainReputationTracker."""

    @pytest.mark.asyncio
    async def test_healthy_domain(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """A domain with no issues should have score > 80 and be categorized as healthy."""
        # No bounces, no complaints, not blacklisted -> score = 100
        score = await tracker.get_reputation_score("healthy.com")
        assert score > 80
        assert tracker.categorize_domain(score) == "healthy"

    @pytest.mark.asyncio
    async def test_warning_domain(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """A domain with moderate issues should score 60-80 and have halved daily limit."""
        from datetime import date

        today = date.today().isoformat()
        store = mock_redis._store
        # Set bounce rate: 5 bounces / 100 sends = 5% -> penalty = 20
        store[f"bounces:warning.com:{today}"] = "5"
        store[f"sends:warning.com:{today}"] = "100"
        # Set complaints: 2/100 = 2% -> penalty = 20*3 = ... wait, complaint_rate = 2/100 = 0.02
        # complaint_penalty = min(30, int(0.02 * 1000 * 3)) = min(30, 60) = 30... too much
        # Let's use 1 complaint: rate = 0.01, penalty = min(30, int(0.01*1000*3)) = min(30, 30) = 30... still too much
        # Just use bounces: 5% bounce rate -> penalty = min(40, int(0.05*100*4)) = min(40, 20) = 20
        # Score = 100 - 20 = 80. That's borderline. Need score in [60, 80].
        # Let's use 7% bounce rate: penalty = min(40, int(0.07*100*4)) = min(40, 28) = 28
        # Score = 100 - 28 = 72 -> warning
        store[f"bounces:warning.com:{today}"] = "7"
        store[f"sends:warning.com:{today}"] = "100"

        score = await tracker.get_reputation_score("warning.com")
        assert 60 <= score <= 80
        assert tracker.categorize_domain(score) == "warning"

        # Daily limit should be halved
        adjusted = await tracker.get_adjusted_daily_limit("warning.com", 100)
        assert adjusted == 50

    @pytest.mark.asyncio
    async def test_critical_domain(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """A domain with serious issues should score < 60 and have daily limit = 0."""
        from datetime import date

        today = date.today().isoformat()
        store = mock_redis._store
        # High bounce rate: 10% -> penalty = min(40, int(0.10*100*4)) = min(40, 40) = 40
        store[f"bounces:critical.com:{today}"] = "10"
        store[f"sends:critical.com:{today}"] = "100"
        # Blacklisted -> penalty = 30
        store["blacklisted:critical.com"] = "1"
        # Total penalty = 40 + 30 = 70, score = 30

        score = await tracker.get_reputation_score("critical.com")
        assert score < 60
        assert tracker.categorize_domain(score) == "critical"

        # Daily limit should be 0
        adjusted = await tracker.get_adjusted_daily_limit("critical.com", 100)
        assert adjusted == 0

    @pytest.mark.asyncio
    async def test_record_complaint(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """record_complaint should increment the complaints counter in Redis."""
        await tracker.record_complaint("test.com")

        # Verify pipeline was called with incr and expire
        pipe = mock_redis.pipeline()
        pipe.incr.assert_called()
        pipe.expire.assert_called()

    @pytest.mark.asyncio
    async def test_daily_check(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """run_daily_check should store scores in Redis for each domain."""
        domains = ["good.com", "bad.com"]
        from datetime import date

        today = date.today().isoformat()
        store = mock_redis._store
        # bad.com has blacklisted flag
        store["blacklisted:bad.com"] = "1"

        results = await tracker.run_daily_check(domains)

        assert "good.com" in results
        assert "bad.com" in results
        assert results["good.com"]["category"] == "healthy"
        assert results["bad.com"]["score"] < results["good.com"]["score"]

        # Verify scores were stored in Redis
        mock_redis.set.assert_any_call(f"reputation:good.com:{today}", str(results["good.com"]["score"]))
        mock_redis.set.assert_any_call(f"reputation:bad.com:{today}", str(results["bad.com"]["score"]))

    @pytest.mark.asyncio
    async def test_score_calculation(self, tracker: DomainReputationTracker, mock_redis: AsyncMock) -> None:
        """Score should be composite of bounce rate (40%), complaints (30%), blacklist (30%)."""
        from datetime import date

        today = date.today().isoformat()
        store = mock_redis._store

        # Set up: 5% bounce rate, 0.5% complaint rate, blacklisted
        store[f"bounces:mixed.com:{today}"] = "5"
        store[f"sends:mixed.com:{today}"] = "100"
        store[f"complaints:mixed.com:{today}"] = "1"  # 1/100 = 1% -> penalty = min(30, int(0.01*1000*3)) = min(30, 30) = 30
        store["blacklisted:mixed.com"] = "1"

        score = await tracker.get_reputation_score("mixed.com")

        # bounce penalty: min(40, int(0.05*100*4)) = 20
        # complaint penalty: min(30, int(0.01*1000*3)) = 30
        # blacklist penalty: 30
        # total penalty: 80, score: 20
        assert score == 20
        assert tracker.categorize_domain(score) == "critical"
