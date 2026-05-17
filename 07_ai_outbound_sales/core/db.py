from __future__ import annotations
from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=20,
            max_overflow=10,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


class _EngineProxy:
    """Proxy that defers engine creation until first attribute access."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    async def dispose(self):
        global _engine
        if _engine is not None:
            await _engine.dispose()
            _engine = None


class _SessionFactoryProxy:
    """Proxy that defers session factory creation until first call."""

    def __call__(self, *args, **kwargs):
        return _get_session_factory()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_session_factory(), name)


engine = _EngineProxy()
async_session_factory = _SessionFactoryProxy()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
