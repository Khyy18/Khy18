"""Tests for database repository using real aiosqlite in-memory database."""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

import aiosqlite

from db.models import SCHEMA


@pytest.fixture
async def db():
    """Create a fresh in-memory database for each test."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
def patch_get_db(db):
    """Patch get_db to return our test database connection."""

    async def _get_db():
        return db

    # We need to patch close to be a no-op so tests can reuse the connection
    original_close = db.close

    async def noop_close():
        pass

    db.close = noop_close

    with patch("db.repository.get_db", new=_get_db):
        yield

    db.close = original_close


@pytest.mark.asyncio
async def test_get_or_create_user_creates_new(patch_get_db, db):
    """Test creating a new user returns correct data."""
    from db.repository import get_or_create_user

    user = await get_or_create_user(12345, "testuser", "Test")

    assert user["user_id"] == 12345
    assert user["username"] == "testuser"
    assert user["first_name"] == "Test"
    assert user["exchanges_count"] == 0
    assert user["total_volume"] == 0.0


@pytest.mark.asyncio
async def test_get_or_create_user_returns_existing(patch_get_db, db):
    """Test that existing user is returned without creating duplicate."""
    from db.repository import get_or_create_user

    # Create user first
    await get_or_create_user(12345, "testuser", "Test")
    # Get same user again
    user = await get_or_create_user(12345, "different", "Name")

    # Should return original data, not the new params
    assert user["user_id"] == 12345
    assert user["username"] == "testuser"


@pytest.mark.asyncio
async def test_create_exchange(patch_get_db, db):
    """Test creating an exchange record."""
    from db.repository import create_exchange, get_exchange_by_id

    row_id = await create_exchange(
        user_id=12345,
        from_currency="BTC",
        to_currency="ETH",
        amount=1.0,
        estimated_amount=15.5,
        provider="changenow",
        payout_address="0xwallet",
        markup_amount=0.225,
        fixed_rate_id="rate-abc",
    )

    assert row_id is not None
    assert row_id > 0

    # Verify the data was actually stored
    exchange = await get_exchange_by_id(row_id)
    assert exchange is not None
    assert exchange["from_currency"] == "BTC"
    assert exchange["to_currency"] == "ETH"
    assert exchange["amount"] == 1.0
    assert exchange["estimated_amount"] == 15.5
    assert exchange["provider"] == "changenow"
    assert exchange["status"] == "new"
    assert exchange["markup_amount"] == 0.225
    assert exchange["fixed_rate_id"] == "rate-abc"


@pytest.mark.asyncio
async def test_update_exchange(patch_get_db, db):
    """Test updating exchange fields."""
    from db.repository import create_exchange, update_exchange, get_exchange_by_id

    row_id = await create_exchange(
        user_id=12345,
        from_currency="BTC",
        to_currency="ETH",
        amount=1.0,
        estimated_amount=15.0,
        provider="changenow",
        payout_address="0xwallet",
    )

    await update_exchange(row_id, status="waiting", exchange_id="cn-123", deposit_address="0xdeposit")

    exchange = await get_exchange_by_id(row_id)
    assert exchange["status"] == "waiting"
    assert exchange["exchange_id"] == "cn-123"
    assert exchange["deposit_address"] == "0xdeposit"
    assert exchange["updated_at"] is not None


@pytest.mark.asyncio
async def test_get_active_exchanges(patch_get_db, db):
    """Test retrieving active exchanges."""
    from db.repository import create_exchange, update_exchange, get_active_exchanges

    # Create exchanges with different statuses
    id1 = await create_exchange(12345, "BTC", "ETH", 1.0, 15.0, "cn", "0x1")
    id2 = await create_exchange(12345, "ETH", "USDT", 10.0, 15000.0, "cn", "0x2")
    id3 = await create_exchange(12345, "BTC", "USDT", 0.5, 30000.0, "cn", "0x3")

    await update_exchange(id1, status="waiting")
    await update_exchange(id2, status="finished")
    await update_exchange(id3, status="exchanging")

    active = await get_active_exchanges()

    # Only "waiting" and "exchanging" are active, not "finished"
    assert len(active) == 2
    statuses = {e["status"] for e in active}
    assert "waiting" in statuses
    assert "exchanging" in statuses
    assert "finished" not in statuses


@pytest.mark.asyncio
async def test_get_user_active_exchanges(patch_get_db, db):
    """Test retrieving active exchanges for a specific user."""
    from db.repository import create_exchange, update_exchange, get_user_active_exchanges

    # User 1 exchanges
    id1 = await create_exchange(111, "BTC", "ETH", 1.0, 15.0, "cn", "0x1")
    await update_exchange(id1, status="waiting")

    # User 2 exchanges
    id2 = await create_exchange(222, "ETH", "USDT", 5.0, 7500.0, "cn", "0x2")
    await update_exchange(id2, status="sending")

    user1_active = await get_user_active_exchanges(111)
    user2_active = await get_user_active_exchanges(222)

    assert len(user1_active) == 1
    assert user1_active[0]["user_id"] == 111
    assert len(user2_active) == 1
    assert user2_active[0]["user_id"] == 222


@pytest.mark.asyncio
async def test_get_exchange_by_exchange_id(patch_get_db, db):
    """Test finding exchange by provider exchange ID."""
    from db.repository import create_exchange, update_exchange, get_exchange_by_exchange_id

    row_id = await create_exchange(12345, "BTC", "ETH", 1.0, 15.0, "cn", "0x1")
    await update_exchange(row_id, exchange_id="provider-xyz-789")

    result = await get_exchange_by_exchange_id("provider-xyz-789")
    assert result is not None
    assert result["exchange_id"] == "provider-xyz-789"
    assert result["from_currency"] == "BTC"

    # Non-existent ID
    result = await get_exchange_by_exchange_id("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_daily_stats(patch_get_db, db):
    """Test daily statistics aggregation."""
    from db.repository import create_exchange, update_exchange, get_daily_stats

    # Create several exchanges today
    id1 = await create_exchange(111, "BTC", "ETH", 1.0, 15.0, "cn", "0x1", markup_amount=0.1)
    id2 = await create_exchange(222, "ETH", "USDT", 5.0, 7500.0, "cn", "0x2", markup_amount=0.5)
    id3 = await create_exchange(333, "BTC", "USDT", 2.0, 60000.0, "cn", "0x3", markup_amount=0.3)

    await update_exchange(id1, status="finished")
    await update_exchange(id2, status="finished")
    await update_exchange(id3, status="failed")

    stats = await get_daily_stats()

    assert stats["total_count"] == 3
    assert stats["total_volume"] == 8.0  # 1.0 + 5.0 + 2.0
    assert abs(stats["total_profit"] - 0.9) < 0.01  # 0.1 + 0.5 + 0.3
    assert stats["completed"] == 2
    assert stats["failed"] == 1


@pytest.mark.asyncio
async def test_increment_user_stats(patch_get_db, db):
    """Test incrementing user exchange count and volume."""
    from db.repository import get_or_create_user, increment_user_stats

    await get_or_create_user(12345, "user", "User")
    await increment_user_stats(12345, 1.5)
    await increment_user_stats(12345, 2.5)

    # Check the user was updated
    cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (12345,))
    row = await cursor.fetchone()
    user = dict(row)

    assert user["exchanges_count"] == 2
    assert user["total_volume"] == 4.0  # 1.5 + 2.5


@pytest.mark.asyncio
async def test_get_failed_exchanges(patch_get_db, db):
    """Test retrieving failed/refunded exchanges."""
    from db.repository import create_exchange, update_exchange, get_failed_exchanges

    id1 = await create_exchange(111, "BTC", "ETH", 1.0, 15.0, "cn", "0x1")
    id2 = await create_exchange(222, "ETH", "USDT", 5.0, 7500.0, "cn", "0x2")
    id3 = await create_exchange(333, "BTC", "USDT", 2.0, 60000.0, "cn", "0x3")

    await update_exchange(id1, status="failed")
    await update_exchange(id2, status="refunded")
    await update_exchange(id3, status="finished")

    failed = await get_failed_exchanges()

    assert len(failed) == 2
    statuses = {e["status"] for e in failed}
    assert "failed" in statuses
    assert "refunded" in statuses
    assert "finished" not in statuses
