"""Tests for PostgreSQL backend: mocked asyncpg pool and CRUD operations."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import db_postgres


@pytest.fixture(autouse=True)
def reset_pool():
    """Reset the module-level pool between tests."""
    db_postgres._pool = None
    yield
    db_postgres._pool = None


@pytest.mark.asyncio
class TestDbPostgres:

    async def test_init_db_creates_pool(self, monkeypatch):
        """init_db creates a connection pool via asyncpg.create_pool."""
        monkeypatch.setattr("db_postgres.config.DATABASE_URL", "postgresql://localhost/test")

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        # Make acquire() work as async context manager
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_asyncpg = MagicMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        monkeypatch.setattr(db_postgres, "asyncpg", mock_asyncpg)

        await db_postgres.init_db()

        mock_asyncpg.create_pool.assert_called_once()
        assert db_postgres._pool is mock_pool

    async def test_get_or_create_client(self, monkeypatch):
        """get_or_create_client returns client dict when pool is available."""
        mock_conn = AsyncMock()
        # First fetchrow returns None (client doesn't exist)
        # After insert, second fetchrow returns the created client
        mock_conn.fetchrow = AsyncMock(
            side_effect=[
                None,
                {"telegram_id": 123, "username": "test", "first_name": "Test",
                 "balance": 0.0, "total_spent": 0.0},
            ]
        )
        mock_conn.execute = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        db_postgres._pool = mock_pool

        result = await db_postgres.get_or_create_client(123, "test", "Test")

        assert result["telegram_id"] == 123
        assert result["username"] == "test"

    async def test_create_order(self, monkeypatch):
        """create_order inserts order and returns ID."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": 42})

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        db_postgres._pool = mock_pool

        order_id = await db_postgres.create_order(123, "copywriting", "Write text", 500.0)

        assert order_id == 42
        mock_conn.fetchrow.assert_called_once()

    async def test_get_or_create_client_no_pool(self):
        """get_or_create_client returns empty dict when pool is None."""
        db_postgres._pool = None
        result = await db_postgres.get_or_create_client(123)
        assert result == {}

    async def test_create_order_no_pool(self):
        """create_order returns 0 when pool is None."""
        db_postgres._pool = None
        result = await db_postgres.create_order(123, "rewrite", "text", 100.0)
        assert result == 0
