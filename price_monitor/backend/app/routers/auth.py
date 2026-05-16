"""Auth router - Telegram initData verification and JWT token issuance."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import create_access_token, verify_telegram_init_data

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/telegram", response_model=TokenResponse)
async def auth_telegram(
    data: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Telegram initData for a JWT access token.

    Verifies the Telegram WebApp initData signature, finds or creates
    the user, and returns a Bearer JWT token.
    """
    user_data = verify_telegram_init_data(data.init_data)
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидные данные Telegram",
        )

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует ID пользователя Telegram",
        )

    # Find or create user
    result = await db.execute(select(User).where(User.telegram_id == int(telegram_id)))
    user = result.scalar_one_or_none()

    if user is None:
        username = user_data.get("username", "")
        user = User(
            telegram_id=int(telegram_id),
            username=username,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Create JWT token
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)
