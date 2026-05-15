"""Tests for warmup network cross-tenant domain warming."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.email.warmup_network import WarmupNetwork


@pytest.fixture
def warmup_network(session_factory, mock_redis):
    """Create WarmupNetwork instance with mocked dependencies."""
    with patch("channels.email.warmup_network.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_redis
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=session_factory,
        )
        network._redis = mock_redis
        return network


@pytest.mark.asyncio
async def test_get_network_domains(warmup_network, async_session):
    """Test get_network_domains returns tenant domains."""
    from tests.conftest import make_tenant

    # Create tenants
    tenant1 = make_tenant(domain="alpha.com")
    tenant2 = make_tenant(domain="beta.com")
    tenant3 = make_tenant(domain="gamma.com")

    async_session.add_all([tenant1, tenant2, tenant3])
    await async_session.commit()

    domains = await warmup_network.get_network_domains()
    assert "alpha.com" in domains
    assert "beta.com" in domains
    assert "gamma.com" in domains
    assert len(domains) >= 3


@pytest.mark.asyncio
async def test_generate_warmup_pair_picks_different_domain():
    """Test generate_warmup_pair picks different domain and returns valid content."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis"):
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )

    network_domains = ["alpha.com", "beta.com", "gamma.com", "delta.com"]
    sender_domain = "alpha.com"

    sender_email, receiver_email, subject, body = network.generate_warmup_pair(
        sender_domain, network_domains
    )

    # Sender must be from sender_domain
    assert sender_email.endswith(f"@{sender_domain}")
    # Receiver must NOT be from sender_domain
    assert not receiver_email.endswith(f"@{sender_domain}")
    # Content must be non-empty
    assert subject
    assert body
    assert len(subject) > 0
    assert len(body) > 10


@pytest.mark.asyncio
async def test_generate_warmup_pair_raises_on_single_domain():
    """Test generate_warmup_pair raises ValueError when no other domains available."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis"):
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )

    with pytest.raises(ValueError, match="No other domains available"):
        network.generate_warmup_pair("only.com", ["only.com"])


@pytest.mark.asyncio
async def test_schedule_network_warmup_spreads_sends():
    """Test schedule_network_warmup spreads sends (no two within 5 min)."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis"):
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )

    schedule = network.schedule_network_warmup("test.com", daily_quota=10)

    assert len(schedule) == 10

    # Convert to minutes and verify minimum gap
    send_minutes = []
    for item in schedule:
        total_minutes = item["send_at_hour"] * 60 + item["send_at_minute"]
        send_minutes.append(total_minutes)

    # Verify all sends are within working hours (8am-6pm)
    for m in send_minutes:
        assert m >= 8 * 60  # >= 8:00 AM
        assert m <= 18 * 60  # <= 6:00 PM

    # Verify minimum gap of 5 minutes between consecutive sends
    sorted_minutes = sorted(send_minutes)
    for i in range(1, len(sorted_minutes)):
        gap = sorted_minutes[i] - sorted_minutes[i - 1]
        assert gap >= 5, f"Gap between send {i-1} and {i} is only {gap} minutes"


@pytest.mark.asyncio
async def test_schedule_network_warmup_zero_quota():
    """Test schedule_network_warmup returns empty for zero quota."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis"):
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )

    schedule = network.schedule_network_warmup("test.com", daily_quota=0)
    assert schedule == []


@pytest.mark.asyncio
async def test_simulate_engagement_records_open(warmup_network, mock_redis):
    """Test simulate_engagement records open event."""
    message_id = str(uuid.uuid4())

    # Pre-set message metadata so domain lookup works
    msg_key = f"warmup_network:message:{message_id}"
    mock_redis._store[msg_key] = "test.com"

    # Mock hget to return domain
    original_hget = mock_redis.hget

    async def mock_hget(key, field=None):
        if key == msg_key and field == "sender_domain":
            return "test.com"
        return None

    mock_redis.hget = AsyncMock(side_effect=mock_hget)
    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock(return_value=1)

    await warmup_network.simulate_engagement(message_id)

    # Verify hset was called to record engagement
    mock_redis.hset.assert_called()
    engagement_key = f"warmup_network:engagement:{message_id}"
    call_args = mock_redis.hset.call_args_list[0]
    assert call_args[0][0] == engagement_key


@pytest.mark.asyncio
async def test_get_network_health(warmup_network, mock_redis):
    """Test get_network_health returns correct stats."""
    # Pre-set Redis values
    mock_redis._store["warmup_network:test.com:sends_today"] = "20"
    mock_redis._store["warmup_network:test.com:opens_today"] = "15"
    mock_redis._store["warmup_network:test.com:replies_today"] = "5"

    health = await warmup_network.get_network_health("test.com")

    assert health["domain"] == "test.com"
    assert health["total_sends"] == 20
    assert health["opens"] == 15
    assert health["replies"] == 5
    assert 0 <= health["health_score"] <= 100
    # Verify health score calculation: (15/20 * 0.6 + 5/20 * 0.4) * 100 = (0.45 + 0.1) * 100 = 55
    assert health["health_score"] in (54, 55)  # Allow for floating point truncation
