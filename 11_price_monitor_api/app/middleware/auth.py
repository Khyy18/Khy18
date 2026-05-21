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
_RATE_LIMIT_MAX_KEYS = 10000  # max unique IPs to track before forced eviction
_rate_limit_last_cleanup = 0.0  # timestamp of last full cleanup
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # run full cleanup every 5 minutes


def _cleanup_rate_limit_store() -> None:
    """Remove stale entries from the rate limit store to prevent memory leaks."""
    global _rate_limit_last_cleanup
    now = time.time()
    if now - _rate_limit_last_cleanup < _RATE_LIMIT_CLEANUP_INTERVAL:
        return
    _rate_limit_last_cleanup = now
    window_start = now - _RATE_LIMIT_WINDOW
    stale_keys = [
        key for key, timestamps in _rate_limit_store.items()
        if not timestamps or all(ts <= window_start for ts in timestamps)
    ]
    for key in stale_keys:
        del _rate_limit_store[key]


def _check_rate_limit(client_ip: str) -> None:
    """Check in-memory rate limit for auth endpoints.

    NOTE: This is a basic in-memory implementation suitable for single-instance
    deployments. For production with multiple workers/instances, replace with
    Redis-based rate limiting (e.g., slowapi with Redis backend).
    """
    # Periodically prune stale keys to prevent unbounded memory growth
    _cleanup_rate_limit_store()

    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    # Clean old entries for current IP
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if ts > window_start
    ]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )
    _rate_limit_store[client_ip].append(now)

    # Hard cap: if store exceeds max keys, remove oldest entries
    if len(_rate_limit_store) > _RATE_LIMIT_MAX_KEYS:
        oldest_keys = sorted(
            _rate_limit_store.keys(),
            key=lambda k: _rate_limit_store[k][-1] if _rate_limit_store[k] else 0,
        )
        for key in oldest_keys[: len(_rate_limit_store) - _RATE_LIMIT_MAX_KEYS]:
            del _rate_limit_store[key]


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
