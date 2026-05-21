"""JWT authentication module for AI Office multi-tenant SaaS."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.config import settings
from ai_office.core.database import get_session
from ai_office.core.models import Tenant, User

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Validate JWT secret key at module import time.
# In dev/test mode (skip_telegram_auth=True), use a fallback dev key.
# In production (skip_telegram_auth=False), the secret MUST be explicitly set.
_DEV_SECRET_FALLBACK = "dev-only-fallback-secret-key"

if not settings.jwt_secret_key:
    if settings.skip_telegram_auth:
        settings.jwt_secret_key = _DEV_SECRET_FALLBACK
    else:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set in production (skip_telegram_auth=False). "
            "Refusing to start with an empty secret."
        )

# Security scheme
security = HTTPBearer(auto_error=False)


# --- Pydantic schemas ---

class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    email: str
    password: str
    company_name: str


class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: str
    password: str


class RefreshRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Response schema with access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response schema for user info."""

    id: str
    email: str
    role: str
    is_super_admin: bool
    tenant_id: str
    tenant_name: str

    model_config = {"from_attributes": True}


# --- Helper functions ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


# --- Dependencies ---

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Extract and validate the current user from JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Check tenant is active (not suspended)
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant and not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is suspended",
        )

    return user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require that the current user is a super admin."""
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


# --- Router ---

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Register a new tenant and admin user."""
    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )

    # Check if email already exists
    result = await session.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create tenant
    tenant = Tenant(
        name=request.company_name,
        email=request.email,
        plan_name="trial",
    )
    session.add(tenant)
    await session.flush()

    # Check if this is the super admin
    is_super_admin = (
        settings.super_admin_email != ""
        and request.email == settings.super_admin_email
    )

    # Create user
    user = User(
        tenant_id=tenant.id,
        email=request.email,
        password_hash=hash_password(request.password),
        role="admin",
        is_super_admin=is_super_admin,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Generate tokens
    token_data = {"sub": user.id, "tenant_id": tenant.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Authenticate user and return tokens."""
    result = await session.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate tokens
    token_data = {"sub": user.id, "tenant_id": user.tenant_id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Refresh access token using a valid refresh token.

    NOTE: Token revocation via a database blocklist is a future improvement.
    Currently, refresh tokens remain valid until natural expiry. For MVP this
    is acceptable but should be addressed before production scale.
    """
    try:
        payload = jwt.decode(
            request.refresh_token, settings.jwt_secret_key, algorithms=[ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        tenant_id: str = payload.get("tenant_id")

        if user_id is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Verify user still exists
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Generate new tokens
    token_data = {"sub": user.id, "tenant_id": tenant_id}
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@auth_router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return current user info with tenant."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_super_admin=current_user.is_super_admin,
        tenant_id=current_user.tenant_id,
        tenant_name=current_user.tenant.name if current_user.tenant else "",
    )
