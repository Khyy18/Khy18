"""
Sessions router: create sessions, list sessions, get profile.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import get_current_user_id
from app.config import settings
from app.models.database import (
    async_session_factory,
    User,
    Session,
    SessionStatus,
)

router = APIRouter(tags=["sessions"])


class SessionResponse(BaseModel):
    id: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    total_cost: str = "0.00"
    rate_per_minute: str = "5.00"


class ProfileResponse(BaseModel):
    id: str
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    balance: str
    rate_per_minute: str


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get current user profile including balance and rate."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return ProfileResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            balance=str(user.balance),
            rate_per_minute=str(settings.RATE_PER_MINUTE),
        )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(user_id: str = Depends(get_current_user_id)):
    """List all sessions for the current user."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.started_at.desc())
        )
        sessions_list = result.scalars().all()

        return [
            SessionResponse(
                id=s.id,
                status=s.status.value if s.status else "active",
                started_at=s.started_at.isoformat() if s.started_at else None,
                ended_at=s.ended_at.isoformat() if s.ended_at else None,
                total_cost=str(s.total_cost or Decimal("0.00")),
                rate_per_minute=str(s.rate_per_minute or Decimal("5.00")),
            )
            for s in sessions_list
        ]


@router.post("/sessions", response_model=SessionResponse)
async def create_session(user_id: str = Depends(get_current_user_id)):
    """
    Create a new active session for the current user.
    Verifies the user has sufficient balance before creating.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.balance < settings.RATE_PER_MINUTE:
            raise HTTPException(
                status_code=402,
                detail="Insufficient balance to start a session",
            )

        # Проверяем, нет ли уже активной сессии у пользователя
        active_check = await session.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.status == SessionStatus.active,
            )
        )
        if active_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="User already has an active session",
            )

        new_session = Session(
            user_id=user_id,
            status=SessionStatus.active,
            rate_per_minute=settings.RATE_PER_MINUTE,
        )
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)

        # Запускаем per-session billing task
        from app.billing.instance import billing_worker
        await billing_worker.start_session_billing(
            new_session.id, user_id, settings.RATE_PER_MINUTE
        )

        return SessionResponse(
            id=new_session.id,
            status=new_session.status.value,
            started_at=new_session.started_at.isoformat() if new_session.started_at else None,
            ended_at=None,
            total_cost=str(new_session.total_cost or Decimal("0.00")),
            rate_per_minute=str(new_session.rate_per_minute or Decimal("5.00")),
        )
