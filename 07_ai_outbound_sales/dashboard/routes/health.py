"""Enhanced health check router with per-dependency status."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_postgres() -> dict[str, Any]:
    """Check PostgreSQL connectivity by attempting a simple query."""
    try:
        from core.db import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "detail": "connection OK"}
    except Exception as exc:
        logger.warning("PostgreSQL health check failed: %s", exc)
        return {"status": "unhealthy", "detail": str(exc)}


async def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity via PING."""
    try:
        import redis.asyncio as aioredis
        from core.config import settings

        client = aioredis.from_url(settings.redis_url)
        try:
            pong = await client.ping()
            if pong:
                return {"status": "healthy", "detail": "PONG received"}
            return {"status": "unhealthy", "detail": "no PONG response"}
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "unhealthy", "detail": str(exc)}


def _check_stripe() -> dict[str, Any]:
    """Validate Stripe secret key format (sk_live_* or sk_test_*)."""
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        return {"status": "degraded", "detail": "key not configured"}
    if key.startswith("sk_live_") or key.startswith("sk_test_"):
        return {"status": "healthy", "detail": "key format valid"}
    return {"status": "degraded", "detail": "unexpected key format"}


def _check_twilio() -> dict[str, Any]:
    """Validate Twilio Account SID format (AC...)."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    if not sid:
        return {"status": "degraded", "detail": "SID not configured"}
    if sid.startswith("AC") and len(sid) == 34:
        return {"status": "healthy", "detail": "SID format valid"}
    return {"status": "degraded", "detail": "unexpected SID format"}


def _check_deepgram() -> dict[str, Any]:
    """Validate Deepgram API key presence."""
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        return {"status": "degraded", "detail": "key not configured"}
    return {"status": "healthy", "detail": "key present"}


def _check_elevenlabs() -> dict[str, Any]:
    """Validate ElevenLabs API key presence."""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        return {"status": "degraded", "detail": "key not configured"}
    return {"status": "healthy", "detail": "key present"}


@router.get("/health/detailed/enhanced")
async def health_detailed_enhanced(request: Request) -> JSONResponse:
    """Enhanced detailed health check with per-service dependency status.

    Returns overall status: healthy, degraded, or unhealthy based on
    individual dependency checks.
    """
    checks: dict[str, dict[str, Any]] = {}

    # Async checks
    checks["postgresql"] = await _check_postgres()
    checks["redis"] = await _check_redis()

    # Sync checks (format validation)
    checks["stripe"] = _check_stripe()
    checks["twilio"] = _check_twilio()
    checks["deepgram"] = _check_deepgram()
    checks["elevenlabs"] = _check_elevenlabs()

    # Determine overall status
    has_unhealthy = any(c["status"] == "unhealthy" for c in checks.values())
    has_degraded = any(c["status"] == "degraded" for c in checks.values())

    if has_unhealthy:
        overall = "unhealthy"
        status_code = 503
    elif has_degraded:
        overall = "degraded"
        status_code = 200
    else:
        overall = "healthy"
        status_code = 200

    return JSONResponse(
        content={
            "overall_status": overall,
            "services": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status_code=status_code,
    )
