"""JWT authentication and Telegram initData verification middleware."""
from __future__ import annotations


import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Maximum age of auth_date before it's considered expired (24 hours)
_AUTH_DATE_MAX_AGE = 86400

def create_access_token(data: dict) -> str:
    """Create a JWT access token."""

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)

def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

def verify_telegram_init_data(init_data: str) -> dict | None:
    """Verify Telegram WebApp initData signature.

    Returns parsed user data if valid, None otherwise.
    """
    if not settings.telegram_bot_token:
        # In dev mode without bot token, try to parse user data directly
        try:
            parsed = parse_qs(init_data)
            user_str = parsed.get("user", [None])[0]
            if user_str:
                return json.loads(user_str)
        except Exception:
            pass
        return None

    try:
        parsed = parse_qs(init_data)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Build data-check-string
        data_pairs = []
        for key, values in sorted(parsed.items()):
            if key != "hash":
                data_pairs.append(f"{key}={values[0]}")
        data_check_string = "\n".join(data_pairs)

        # Compute HMAC
        secret_key = hmac.HMAC(
            b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.HMAC(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if computed_hash != received_hash:
            return None

        # Check auth_date expiry
        auth_date_str = parsed.get("auth_date", [None])[0]
        if auth_date_str:
            try:
                auth_date = int(auth_date_str)
                if time.time() - auth_date > _AUTH_DATE_MAX_AGE:
                    logger.warning("Telegram initData expired: auth_date=%s", auth_date_str)
                    return None
            except (ValueError, TypeError):
                pass

        user_str = parsed.get("user", [None])[0]
        if user_str:
            return json.loads(user_str)
        return None
    except Exception as e:
        logger.warning("Telegram initData verification failed: %s", e)
        return None

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency to get the current authenticated user."""
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
        )
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    return user

async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that requires the user to be an admin."""
    admin_ids_str = settings.admin_telegram_ids
    admin_ids: list[int] = []
    if admin_ids_str:
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    if settings.telegram_admin_id:
        admin_ids.append(settings.telegram_admin_id)

    if user.telegram_id not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user
