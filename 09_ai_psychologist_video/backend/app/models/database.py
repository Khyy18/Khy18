import uuid
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column, String, BigInteger, Numeric, DateTime, ForeignKey, Enum, func
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship

from app.config import settings


class Base(DeclarativeBase):
    pass


class SessionStatus(str, enum.Enum):
    active = "active"
    finished = "finished"


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    debit = "debit"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    balance = Column(Numeric(precision=12, scale=2), default=Decimal("0.00"))
    created_at = Column(DateTime, server_default=func.now())

    sessions = relationship("Session", back_populates="user", lazy="selectin")
    transactions = relationship("Transaction", back_populates="user", lazy="selectin")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(SessionStatus), default=SessionStatus.active)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    total_cost = Column(Numeric(precision=12, scale=2), default=Decimal("0.00"))
    rate_per_minute = Column(Numeric(precision=10, scale=2), default=Decimal("5.00"))

    user = relationship("User", back_populates="sessions")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    source = Column(String, nullable=True)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.completed)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="transactions")


async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Создание всех таблиц в базе данных."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
