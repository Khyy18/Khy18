"""
Sessions router: create sessions, list sessions, get profile, session summary.
"""

import logging
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
    SessionNote,
)

logger = logging.getLogger(__name__)

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


class SessionSummaryResponse(BaseModel):
    summary: str
    homework: str | None = None
    mood_score: int | None = None
    duration: float | None = None
    cost: str | None = None


@router.get("/sessions/{session_id}/summary", response_model=SessionSummaryResponse)
async def get_session_summary(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Получение саммари сессии. Если уже есть в session_notes - возвращает кэш.
    Если нет - генерирует через LLM (или mock при отсутствии LLM_API_KEY).
    """
    async with async_session_factory() as session:
        # Проверяем что сессия принадлежит пользователю
        session_result = await session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.user_id == user_id,
            )
        )
        user_session = session_result.scalar_one_or_none()
        if not user_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Проверяем кэш в session_notes
        note_result = await session.execute(
            select(SessionNote).where(SessionNote.session_id == session_id)
        )
        existing_note = note_result.scalar_one_or_none()

        if existing_note:
            # Возвращаем кэшированное саммари
            duration = None
            if user_session.started_at and user_session.ended_at:
                duration = (user_session.ended_at - user_session.started_at).total_seconds() / 60.0

            return SessionSummaryResponse(
                summary=existing_note.summary or "",
                homework=existing_note.homework,
                mood_score=existing_note.mood_score,
                duration=round(duration, 2) if duration else None,
                cost=str(user_session.total_cost or Decimal("0.00")),
            )

        # Генерируем саммари
        summary_text = ""
        homework_text = None
        mood = None

        if settings.LLM_API_KEY:
            # Реальная генерация через LLM
            try:
                summary_text, homework_text, mood = await _generate_summary_via_llm(session_id)
            except Exception as e:
                logger.error(f"LLM summary generation failed: {e}")
                summary_text = "Сессия завершена. Саммари временно недоступно."
        else:
            # Mock при отсутствии API ключа
            summary_text = (
                "Сессия прошла продуктивно. Обсуждались актуальные переживания "
                "и стратегии совладания со стрессом."
            )
            homework_text = "Вести дневник эмоций в течение недели."
            mood = 7

        # Сохраняем в session_notes
        note = SessionNote(
            session_id=session_id,
            summary=summary_text,
            homework=homework_text,
            mood_score=mood,
        )
        session.add(note)
        await session.commit()

        duration = None
        if user_session.started_at and user_session.ended_at:
            duration = (user_session.ended_at - user_session.started_at).total_seconds() / 60.0

        return SessionSummaryResponse(
            summary=summary_text,
            homework=homework_text,
            mood_score=mood,
            duration=round(duration, 2) if duration else None,
            cost=str(user_session.total_cost or Decimal("0.00")),
        )


async def _generate_summary_via_llm(session_id: str) -> tuple[str, str | None, int | None]:
    """
    Генерация саммари через LLM провайдер (fallback-путь).

    Основной путь генерации саммари - через pipeline.get_summary() во время активной
    WebSocket-сессии. Этот метод сохраняет результат в SessionNote.
    Данный endpoint служит фоллбеком для случаев, когда SessionNote не был создан
    (например, при сбое соединения). Поскольку история разговора хранится только
    в оперативной памяти pipeline и теряется после завершения сессии, эта функция
    генерирует общее саммари без контекста конкретной сессии.

    Возвращает (summary, homework, mood_score).
    """
    prompt = (
        "Ты - AI психолог. Сессия завершена, но детальная запись недоступна. "
        "Сгенерируй общее саммари для завершенной консультации, "
        "домашнее задание для клиента и оценку настроения (1-10).\n"
        "Ответь в формате:\n"
        "SUMMARY: ...\n"
        "HOMEWORK: ...\n"
        "MOOD: число от 1 до 10"
    )

    if settings.LLM_PROVIDER == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY)
        response = await client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
    else:
        # OpenAI-compatible
        import openai

        client = openai.AsyncOpenAI(api_key=settings.LLM_API_KEY)
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""

    # Парсим ответ
    summary = ""
    homework = None
    mood = None

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
        elif line.startswith("HOMEWORK:"):
            homework = line[len("HOMEWORK:"):].strip()
        elif line.startswith("MOOD:"):
            try:
                mood = int(line[len("MOOD:"):].strip())
            except ValueError:
                mood = None

    if not summary:
        summary = text[:500]  # fallback: используем весь текст

    return summary, homework, mood
