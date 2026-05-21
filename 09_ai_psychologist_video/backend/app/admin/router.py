"""
Административная панель: статистика, управление пользователями и сессиями.
Все эндпоинты защищены X-Admin-Key заголовком.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from app.config import settings
from app.models.database import (
    async_session_factory,
    User,
    Session,
    Transaction,
    TransactionType,
    SessionStatus,
)

router = APIRouter(prefix="/admin", tags=["admin"])


async def verify_admin_key(x_admin_key: str = Header(...)) -> str:
    """Проверка административного ключа из заголовка запроса."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=503, detail="Admin API key not configured"
        )
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return x_admin_key


class StatsResponse(BaseModel):
    total_users: int
    total_sessions: int
    revenue_today: str


class UserItem(BaseModel):
    id: str
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    balance: str
    session_count: int
    created_at: str | None = None


class SessionItem(BaseModel):
    id: str
    user_id: str
    username: str | None = None
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    total_cost: str


class PaginatedUsers(BaseModel):
    items: list[UserItem]
    total: int
    page: int
    per_page: int


class PaginatedSessions(BaseModel):
    items: list[SessionItem]
    total: int
    page: int
    per_page: int


class MetricsResponse(BaseModel):
    active_sessions_count: int
    revenue_today: str
    avg_session_duration_minutes: float


@router.get("/stats", response_model=StatsResponse)
async def get_stats(_: str = Depends(verify_admin_key)):
    """Общая статистика: пользователи, сессии, доход за сегодня."""
    async with async_session_factory() as session:
        # Количество пользователей
        users_count = await session.execute(select(func.count(User.id)))
        total_users = users_count.scalar() or 0

        # Количество сессий
        sessions_count = await session.execute(select(func.count(Session.id)))
        total_sessions = sessions_count.scalar() or 0

        # Доход за сегодня (сумма deposit-транзакций за текущий день)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        revenue_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.deposit,
                Transaction.created_at >= today_start,
            )
        )
        revenue_today = revenue_result.scalar() or Decimal("0.00")

        return StatsResponse(
            total_users=total_users,
            total_sessions=total_sessions,
            revenue_today=str(revenue_today),
        )


@router.get("/sessions", response_model=PaginatedSessions)
async def list_sessions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_admin_key),
):
    """Пагинированный список сессий с информацией о пользователе."""
    async with async_session_factory() as session:
        # Общее количество
        total_result = await session.execute(select(func.count(Session.id)))
        total = total_result.scalar() or 0

        # Выборка с пагинацией
        offset = (page - 1) * per_page
        result = await session.execute(
            select(Session, User.username)
            .join(User, Session.user_id == User.id)
            .order_by(Session.started_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = result.all()

        items = [
            SessionItem(
                id=s.id,
                user_id=s.user_id,
                username=username,
                status=s.status.value if s.status else "unknown",
                started_at=s.started_at.isoformat() if s.started_at else None,
                ended_at=s.ended_at.isoformat() if s.ended_at else None,
                total_cost=str(s.total_cost or Decimal("0.00")),
            )
            for s, username in rows
        ]

        return PaginatedSessions(
            items=items, total=total, page=page, per_page=per_page
        )


@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_admin_key),
):
    """Пагинированный список пользователей с количеством сессий и балансом."""
    async with async_session_factory() as session:
        # Общее количество пользователей
        total_result = await session.execute(select(func.count(User.id)))
        total = total_result.scalar() or 0

        # Выборка с пагинацией и подсчетом сессий
        offset = (page - 1) * per_page
        result = await session.execute(
            select(User, func.count(Session.id).label("session_count"))
            .outerjoin(Session, User.id == Session.user_id)
            .group_by(User.id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = result.all()

        items = [
            UserItem(
                id=user.id,
                telegram_id=user.telegram_id,
                username=user.username,
                first_name=user.first_name,
                balance=str(user.balance),
                session_count=session_count,
                created_at=user.created_at.isoformat() if user.created_at else None,
            )
            for user, session_count in rows
        ]

        return PaginatedUsers(
            items=items, total=total, page=page, per_page=per_page
        )


@router.post("/metrics", response_model=MetricsResponse)
async def get_metrics(_: str = Depends(verify_admin_key)):
    """Метрики: активные сессии, доход за сегодня, средняя длительность сессии."""
    async with async_session_factory() as session:
        # Активные сессии
        active_result = await session.execute(
            select(func.count(Session.id)).where(
                Session.status == SessionStatus.active
            )
        )
        active_sessions_count = active_result.scalar() or 0

        # Доход за сегодня
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        revenue_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.deposit,
                Transaction.created_at >= today_start,
            )
        )
        revenue_today = revenue_result.scalar() or Decimal("0.00")

        # Средняя длительность завершенных сессий (в минутах)
        # Для SQLite используем простой подход через Python
        finished_result = await session.execute(
            select(Session.started_at, Session.ended_at).where(
                Session.status == SessionStatus.finished,
                Session.ended_at.isnot(None),
            )
        )
        finished_sessions = finished_result.all()

        avg_duration = 0.0
        if finished_sessions:
            durations = []
            for started_at, ended_at in finished_sessions:
                if started_at and ended_at:
                    delta = (ended_at - started_at).total_seconds() / 60.0
                    durations.append(delta)
            if durations:
                avg_duration = sum(durations) / len(durations)

        return MetricsResponse(
            active_sessions_count=active_sessions_count,
            revenue_today=str(revenue_today),
            avg_session_duration_minutes=round(avg_duration, 2),
        )
