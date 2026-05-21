import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.auth.telegram import validate_init_data
from app.auth.jwt import create_token
from app.models.database import async_session_factory, User, Transaction, TransactionType

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data_raw: str
    start_param: str | None = None  # Параметр ?start= из deep link (для рефералов)


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
            # Обработка реферального параметра при регистрации
            referred_by = None
            start_param = request.start_param or data.get("start_param", "")
            if start_param and start_param.startswith("ref_"):
                referrer_id = start_param[4:]  # Убираем префикс "ref_"
                # Проверяем что реферер существует
                referrer_result = await session.execute(
                    select(User).where(User.id == referrer_id)
                )
                referrer = referrer_result.scalar_one_or_none()
                if referrer:
                    referred_by = referrer_id
                    # Начисляем бонус рефереру (50 руб)
                    from decimal import Decimal
                    referral_bonus = Decimal("50.00")
                    referrer.balance = referrer.balance + referral_bonus
                    tx = Transaction(
                        user_id=referrer_id,
                        amount=referral_bonus,
                        type=TransactionType.deposit,
                        source=f"referral:{telegram_id}",
                    )
                    session.add(tx)

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                referred_by=referred_by,
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
