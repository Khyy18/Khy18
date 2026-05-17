"""SQLAlchemy async database setup with PostgreSQL models."""

import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


class User(Base):
    """User model for persistent storage."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    balance = Column(Integer, default=0, nullable=False)

    sessions = relationship("Session", back_populates="user")


class Session(Base):
    """Session model for tracking call sessions."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    natal_chart_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="sessions")


class BillingEventLog(Base):
    """Billing event log for audit trail."""

    __tablename__ = "billing_event_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    event_type = Column(String(32), nullable=False)
    amount = Column(Integer, default=0, nullable=False)
    balance_after = Column(Integer, default=0, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


# Module-level engine and session maker
_engine: Optional[AsyncEngine] = None
_async_session: Optional[async_sessionmaker[AsyncSession]] = None


async def init_database() -> Optional[AsyncEngine]:
    """Initialize the database engine and create tables.

    Only initializes if DATABASE_URL is configured.
    Returns the engine or None if not configured.
    """
    global _engine, _async_session

    if not settings.database_url:
        logger.info("DATABASE_URL not set, PostgreSQL persistence disabled")
        return None

    # Convert postgres:// to postgresql+asyncpg:// if needed
    db_url = settings.database_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(db_url, echo=False, pool_size=10, max_overflow=20)
    _async_session = async_sessionmaker(_engine, expire_on_commit=False)

    # Create tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized and tables created")
    return _engine


async def close_database() -> None:
    """Close the database engine."""
    global _engine, _async_session
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session = None
        logger.info("Database connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session.

    Yields an AsyncSession. If database is not configured, raises an error.
    """
    if _async_session is None:
        raise RuntimeError("Database not initialized. Set DATABASE_URL to enable persistence.")
    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
