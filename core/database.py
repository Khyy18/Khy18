"""Асинхронное подключение к базе данных через SQLAlchemy 2.0."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ai_office.core.config import settings

# Асинхронный движок SQLAlchemy
engine = create_async_engine(
    settings.database_url,
    echo=False,
)

# Фабрика асинхронных сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    pass


async def get_session() -> AsyncSession:
    """Получить асинхронную сессию БД."""
    async with async_session() as session:
        yield session


async def init_db():
    """Создать все таблицы в базе данных."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
