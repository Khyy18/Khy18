"""Эндпоинты реферальной системы."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import (
    ReferralApplyRequest,
    ReferralApplyResponse,
    ReferralCodeResponse,
    ReferralStatsResponse,
)
from ai_office.core.database import get_session
from ai_office.core.referral import apply_referral, generate_referral_code, get_referral_stats

router = APIRouter(prefix="/api/referral", tags=["referral"])


@router.get("/stats", response_model=ReferralStatsResponse)
async def referral_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Получить статистику рефералов текущего пользователя."""
    telegram_id = getattr(request.state, "user_telegram_id", 0)
    stats = await get_referral_stats(telegram_id, session)
    return ReferralStatsResponse(**stats)


@router.get("/code", response_model=ReferralCodeResponse)
async def referral_code(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Получить или сгенерировать реферальный код."""
    telegram_id = getattr(request.state, "user_telegram_id", 0)
    code = await generate_referral_code(telegram_id, session)
    referral_link = f"https://t.me/ai_office_bot?start=ref_{code}"
    return ReferralCodeResponse(code=code, referral_link=referral_link)


@router.post("/apply", response_model=ReferralApplyResponse)
async def referral_apply(
    body: ReferralApplyRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Применить реферальный код."""
    telegram_id = getattr(request.state, "user_telegram_id", 0)
    result = await apply_referral(telegram_id, body.code, session)
    return ReferralApplyResponse(**result)
