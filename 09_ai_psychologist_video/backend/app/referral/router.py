"""
Реферальная система: статистика рефералов, генерация реферальной ссылки.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from app.auth.dependencies import get_current_user_id
from app.config import settings
from app.models.database import async_session_factory, User

router = APIRouter(prefix="/referral", tags=["referral"])


class ReferralStatsResponse(BaseModel):
    referral_count: int
    total_earned: str


class ReferralLinkResponse(BaseModel):
    link: str


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(user_id: str = Depends(get_current_user_id)):
    """
    Статистика рефералов: количество приглашенных и суммарный заработок.
    Бонус за каждого реферала: 50 руб (фиксированный).
    """
    async with async_session_factory() as session:
        # Считаем пользователей, которых пригласил текущий user
        result = await session.execute(
            select(func.count(User.id)).where(User.referred_by == user_id)
        )
        referral_count = result.scalar() or 0

        # Заработок = количество рефералов * бонус за реферала
        bonus_per_referral = Decimal("50.00")
        total_earned = bonus_per_referral * referral_count

        return ReferralStatsResponse(
            referral_count=referral_count,
            total_earned=str(total_earned),
        )


@router.get("/link", response_model=ReferralLinkResponse)
async def get_referral_link(user_id: str = Depends(get_current_user_id)):
    """
    Генерация реферальной ссылки для пользователя.
    Формат: https://t.me/{bot_username}?start=ref_{user_id}
    """
    # Извлекаем username бота из BOT_TOKEN (или используем placeholder)
    bot_username = "ai_psychologist_bot"
    if settings.BOT_TOKEN:
        # BOT_TOKEN формат: 123456:ABC-DEF - username получаем через API,
        # но для генерации ссылки используем фиксированное имя бота
        pass

    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return ReferralLinkResponse(link=link)
