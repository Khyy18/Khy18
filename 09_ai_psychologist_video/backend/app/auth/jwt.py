from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException

from app.config import settings


def create_token(user_id: str) -> str:
    """Создание JWT токена с HS256 алгоритмом, срок действия 24 часа."""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """
    Проверка JWT токена. Возвращает payload при успехе.
    Выбрасывает HTTPException 401 при невалидном/просроченном токене.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
