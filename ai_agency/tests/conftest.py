"""Shared fixtures for AI agency tests."""

import sys
import os
import pytest
import pytest_asyncio

# Add ai_agency to path so imports work like they do in the main app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary SQLite DB path."""
    return str(tmp_path / "test_agency.db")


@pytest.fixture
def mock_config(monkeypatch, db_path):
    """Monkeypatch config.DATABASE_PATH to use temp DB."""
    import config
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(config, "QUEUE_MAX_SIZE", 10)
    monkeypatch.setattr(config, "QUEUE_WORKERS", 2)
    return config


@pytest_asyncio.fixture
async def initialized_db(mock_config):
    """Initialize the database with all tables."""
    import database
    await database.init_db()
    return mock_config


@pytest_asyncio.fixture
async def sample_client(initialized_db):
    """Create a test client in the DB."""
    import database
    client = await database.get_or_create_client(
        telegram_id=12345,
        username="testuser",
        first_name="Test",
    )
    return client
