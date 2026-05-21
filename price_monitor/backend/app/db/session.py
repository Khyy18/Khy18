"""Async database engine and session management."""
from __future__ import annotations


from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

# Use SQLite by default (database_url), PostgreSQL only if explicitly configured via env
import os
_url = os.environ.get("DATABASE_URL", settings.database_url)

engine = create_async_engine(_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """FastAPI dependency that yields an async database session."""

    async with async_session() as session:
        yield session

async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
