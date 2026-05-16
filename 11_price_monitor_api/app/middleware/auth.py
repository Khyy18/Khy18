"""JWT authentication middleware."""

import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db

security = HTTPBearer()

# --- Rate limiting for auth endpoints ---
# In production, use Redis-based rate limiting instead of in-memory.
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window per IP


def _check_rate_limit(client_ip: str) -> None:
    """Check in-memory rate limit for auth endpoints.

    NOTE: This is a basic in-memory implementation suitable for single-instance
    deployments. For production with multiple workers/instances, replace with
    Redis-based rate limiting (e.g., slowapi with Redis backend).
    """
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    # Clean old entries
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if ts > window_start
    ]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )
    _rate_limit_store[client_ip].append(now)


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
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
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
            detail="Invalid token payload",
        )
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that requires the user to be an admin.

    Admin is determined by checking if the user's telegram_id is in the
    ADMIN_TELEGRAM_IDS config setting (comma-separated list).
    """
    admin_ids_str = settings.admin_telegram_ids
    if admin_ids_str:
        admin_ids = [
            int(x.strip()) for x in admin_ids_str.split(",") if x.strip()
        ]
    else:
        admin_ids = []

    # Also allow the single telegram_admin_id from settings
    if settings.telegram_admin_id:
        admin_ids.append(settings.telegram_admin_id)

    if user.telegram_id not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
