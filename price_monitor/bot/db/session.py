"""Async database engine and session management for the bot."""
from __future__ import annotations

import sys
from pathlib import Path

# Add backend directory to path so we can import shared models
_backend_dir = str(Path(__file__).resolve().parent.parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

# Import Base and models from backend
from app.db.models import Base  # noqa: E402

# Use PostgreSQL if configured, fallback to SQLite
_url = settings.postgresql_url if "postgresql" in settings.postgresql_url else settings.database_url

engine = create_async_engine(_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Async context manager that yields a database session."""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    await engine.dispose()
