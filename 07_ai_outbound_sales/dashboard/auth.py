from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Tenant, User, UserRole
from dashboard.schemas import TokenResponse, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer()

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


async def _get_session() -> AsyncGenerator[AsyncSession, None]:
    """Lazy wrapper around core.db.get_session to avoid import-time engine creation."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with automatic salt generation."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return _bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(_get_session),
) -> User:
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def tenant_scope(
    current_user: User = Depends(get_current_user),
) -> UUID:
    return current_user.tenant_id


# NOTE: Open registration is intentional for MVP/development. In production,
# this endpoint should be gated with an invite code, rate limiting, or admin approval.
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate, session: AsyncSession = Depends(_get_session)
) -> User:
    # Check if user already exists
    result = await session.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create tenant
    tenant = Tenant(name=data.tenant_name, domain=data.email.split("@")[1])
    session.add(tenant)
    await session.flush()

    # Create user
    user = User(
        tenant_id=tenant.id,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.admin,
    )
    session.add(user)
    await session.flush()

    # Create Stripe customer and subscription (graceful - log warning if fails)
    stripe_customer_id = None
    try:
        from integrations.billing import StripeClient

        stripe_client = StripeClient(secret_key=settings.stripe_secret_key)
        customer = await stripe_client.create_customer(
            email=data.email,
            name=data.tenant_name,
            metadata={"tenant_id": str(tenant.id)},
        )
        if "error" not in customer:
            stripe_customer_id = customer.get("id")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to create Stripe customer for %s: %s", data.email, exc
        )

    # Create default subscription with starter plan
    try:
        from core.models import Plan, PlanName, Subscription, SubscriptionStatus

        plan_result = await session.execute(
            select(Plan).where(Plan.name == PlanName.starter)
        )
        starter_plan = plan_result.scalar_one_or_none()
        if starter_plan:
            subscription = Subscription(
                tenant_id=tenant.id,
                plan_id=starter_plan.id,
                stripe_customer_id=stripe_customer_id,
                status=SubscriptionStatus.trialing,
            )
            session.add(subscription)
            await session.flush()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to create default subscription for %s: %s", data.email, exc
        )

    await session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin, session: AsyncSession = Depends(_get_session)
) -> dict:
    result = await session.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Refresh an access token. Accepts a valid token and returns a new one."""
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    # Verify user still exists
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    new_token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return {"access_token": new_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the current authenticated user's information."""
    return current_user
