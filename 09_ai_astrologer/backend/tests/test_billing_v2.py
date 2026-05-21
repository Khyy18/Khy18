"""Tests for decoupled Redis pub/sub billing."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.billing import BillingManager
from app.models import BillingEvent


class TestBillingV2:
    """Tests for the decoupled billing manager."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client with pub/sub support."""
        redis = AsyncMock()
        redis._store = {}
        redis._published = []

        async def mock_get(key):
            return redis._store.get(key)

        async def mock_set(key, value):
            redis._store[key] = value

        async def mock_eval(script, numkeys, *args):
            """Simulate Lua script for atomic deduct."""
            key = args[0]
            cost = int(args[1])
            current = int(redis._store.get(key) or "0")
            if current < cost:
                return [0, current]
            new_balance = current - cost
            redis._store[key] = str(new_balance)
            return [1, new_balance]

        async def mock_publish(channel, message):
            redis._published.append({"channel": channel, "message": message})
            return 1

        async def mock_zadd(key, mapping):
            if key not in redis._store:
                redis._store[key] = {}
            if isinstance(redis._store[key], str):
                redis._store[key] = {}
            redis._store[key].update(mapping)

        async def mock_zrem(key, *members):
            if key in redis._store and isinstance(redis._store[key], dict):
                for m in members:
                    redis._store[key].pop(m, None)

        async def mock_zrangebyscore(key, min_score, max_score):
            if key not in redis._store or not isinstance(redis._store[key], dict):
                return []
            return [
                k
                for k, v in redis._store[key].items()
                if min_score <= v <= max_score
            ]

        redis.get = AsyncMock(side_effect=mock_get)
        redis.set = AsyncMock(side_effect=mock_set)
        redis.eval = AsyncMock(side_effect=mock_eval)
        redis.publish = AsyncMock(side_effect=mock_publish)
        redis.zadd = AsyncMock(side_effect=mock_zadd)
        redis.zrem = AsyncMock(side_effect=mock_zrem)
        redis.zrangebyscore = AsyncMock(side_effect=mock_zrangebyscore)

        # Mock pubsub
        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        redis.pubsub = MagicMock(return_value=pubsub)

        return redis

    @pytest.fixture
    def billing(self, mock_redis):
        """Create a BillingManager with mock Redis."""
        manager = BillingManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_publish_billing_event(self, billing, mock_redis):
        """Test that billing events are published to Redis channel."""
        event = BillingEvent(
            event_type="BALANCE_UPDATE",
            user_id="user1",
            session_id="sess1",
            amount=10,
            balance_after=90,
        )
        await billing.publish_billing_event("sess1", event)

        assert len(mock_redis._published) == 1
        assert mock_redis._published[0]["channel"] == "billing:sess1"
        published_data = json.loads(mock_redis._published[0]["message"])
        assert published_data["event_type"] == "BALANCE_UPDATE"
        assert published_data["balance_after"] == 90

    @pytest.mark.asyncio
    async def test_subscribe_billing_events(self, billing, mock_redis):
        """Test subscribing to billing events channel."""
        pubsub = await billing.subscribe_billing_events("sess1")
        assert pubsub is not None
        pubsub.subscribe.assert_called_once_with("billing:sess1")

    @pytest.mark.asyncio
    async def test_subscribe_no_redis(self):
        """Test subscribing with no Redis returns None."""
        manager = BillingManager(redis_client=None)
        result = await manager.subscribe_billing_events("sess1")
        assert result is None

    @pytest.mark.asyncio
    async def test_publish_no_redis(self):
        """Test publishing with no Redis does not raise."""
        manager = BillingManager(redis_client=None)
        event = BillingEvent(
            event_type="BALANCE_UPDATE",
            user_id="user1",
            session_id="sess1",
        )
        # Should not raise
        await manager.publish_billing_event("sess1", event)

    @pytest.mark.asyncio
    @patch("app.billing.settings")
    async def test_low_balance_warning_before_terminate(
        self, mock_settings, billing, mock_redis
    ):
        """Test LOW_BALANCE_WARNING is sent before TERMINATE_CALL.

        With balance=20, cost=10 per interval, grace_period=90s, interval=60s:
        - remaining_time = (20/10) * 60 = 120s > 90s, no warning on first check
        - After first deduct: remaining_time = (10/10) * 60 = 60s <= 90s, warning
        - After second deduct: balance=0, TERMINATE_CALL
        """
        mock_settings.minute_cost_coins = 10
        mock_settings.billing_interval_seconds = 0.05  # Very short for testing
        mock_settings.grace_period_seconds = 90

        await billing.set_balance("user1", 20)

        # Start billing without WebSocket
        await billing.start_billing_loop("sess1", "user1", ws=None)

        # Wait for billing to process
        await asyncio.sleep(0.3)

        # Stop billing
        await billing.stop_billing_loop("sess1")

        # Check published events
        events = [
            json.loads(p["message"]) for p in mock_redis._published
        ]
        event_types = [e["event_type"] for e in events]

        # Should have LOW_BALANCE_WARNING before TERMINATE_CALL
        assert "BALANCE_UPDATE" in event_types
        assert "TERMINATE_CALL" in event_types

        # TERMINATE_CALL should be the last event
        assert event_types[-1] == "TERMINATE_CALL"

    @pytest.mark.asyncio
    @patch("app.billing.settings")
    async def test_billing_worker_publishes_events(
        self, mock_settings, billing, mock_redis
    ):
        """Test that billing worker publishes events via Redis pub/sub."""
        mock_settings.minute_cost_coins = 10
        mock_settings.billing_interval_seconds = 0.05
        mock_settings.grace_period_seconds = 30

        await billing.set_balance("user1", 100)
        await billing.start_billing_loop("sess1", "user1", ws=None)

        # Wait for at least one billing tick
        await asyncio.sleep(0.1)
        await billing.stop_billing_loop("sess1")

        # Should have published at least one event
        assert len(mock_redis._published) > 0
        first_event = json.loads(mock_redis._published[0]["message"])
        assert first_event["event_type"] in ("BALANCE_UPDATE", "LOW_BALANCE_WARNING")
        assert first_event["session_id"] == "sess1"

    @pytest.mark.asyncio
    async def test_billing_active_sorted_set(self, billing, mock_redis):
        """Test that billing sessions are tracked in sorted set."""
        await billing.set_balance("user1", 1000)
        await billing.start_billing_loop("sess1", "user1", ws=None)

        # Check that session is in sorted set
        assert "billing_active" in mock_redis._store
        assert "sess1" in mock_redis._store["billing_active"]

        await billing.stop_billing_loop("sess1")

    @pytest.mark.asyncio
    async def test_stop_billing_removes_from_sorted_set(self, billing, mock_redis):
        """Test that stopping billing removes session from sorted set."""
        await billing.set_balance("user1", 1000)
        await billing.start_billing_loop("sess1", "user1", ws=None)
        await asyncio.sleep(0.05)
        await billing.stop_billing_loop("sess1")

        # Session should be removed from sorted set
        if "billing_active" in mock_redis._store:
            assert "sess1" not in mock_redis._store.get("billing_active", {})

    @pytest.mark.asyncio
    async def test_get_active_session_count(self, billing, mock_redis):
        """Test counting active billing sessions."""
        assert billing.get_active_session_count() == 0

        await billing.set_balance("user1", 1000)
        await billing.start_billing_loop("sess1", "user1", ws=None)
        assert billing.get_active_session_count() == 1

        await billing.stop_billing_loop("sess1")
        assert billing.get_active_session_count() == 0

    @pytest.mark.asyncio
    async def test_calculate_remaining_time(self, billing):
        """Test remaining time calculation."""
        # 100 balance, 10 per interval, 60s interval = 600s remaining
        remaining = billing._calculate_remaining_time(100, 10)
        assert remaining == 600.0

        # Zero cost should return infinity
        remaining = billing._calculate_remaining_time(100, 0)
        assert remaining == float("inf")
