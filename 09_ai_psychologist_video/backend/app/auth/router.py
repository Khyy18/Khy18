import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.auth.telegram import validate_init_data
from app.auth.jwt import create_token
from app.models.database import async_session_factory, User

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data_raw: str


class AuthResponse(BaseModel):
    token: str
    user: dict


@router.post("/telegram", response_model=AuthResponse)
async def auth_telegram(request: TelegramAuthRequest):
    """
    Аутентификация через Telegram WebApp initDataRaw.
    Валидирует подпись, извлекает данные пользователя, создает/обновляет в БД.
    """
    data = validate_init_data(request.init_data_raw, settings.BOT_TOKEN)

    # Извлекаем данные пользователя из parsed data
    user_data_raw = data.get("user")
    if not user_data_raw:
        raise HTTPException(status_code=400, detail="No user data in init_data")

    try:
        user_info = json.loads(user_data_raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user data format")

    telegram_id = user_info.get("id")
    username = user_info.get("username", "")
    first_name = user_info.get("first_name", "")

    if not telegram_id:
        raise HTTPException(status_code=400, detail="Missing telegram user id")

    # Upsert пользователя в базе данных
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name

        await session.commit()
        await session.refresh(user)

        token = create_token(user.id)

        return AuthResponse(
            token=token,
            user={
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "balance": str(user.balance),
            },
        )
