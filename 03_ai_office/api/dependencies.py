"""Shared dependencies for AI Office API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.config import settings
from ai_office.core.database import get_session
from ai_office.core.models import Tenant, User

from ai_office.api.auth import ALGORITHM

# Security scheme that does not raise on missing header
security_optional = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Extract user from JWT if present and valid. Returns None otherwise.

    This dependency never raises exceptions - it simply returns None when:
    - No Authorization header is present
    - The token is invalid or expired
    - The user cannot be found in the database
    - The tenant is suspended
    """
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        if user_id is None or token_type != "access":
            return None
    except JWTError:
        return None

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    # Check tenant is active (not suspended)
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant and not tenant.is_active:
        return None

    return user


def get_tenant_id(user: Optional[User]) -> Optional[str]:
    """Extract tenant_id from user. Returns None if no user."""
    if user is None:
        return None
    return user.tenant_id
