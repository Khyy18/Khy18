"""Authentication: Telegram initData HMAC validation + Bearer token."""

import hashlib
import hmac
from urllib.parse import parse_qs, unquote

from fastapi import Header, HTTPException, status

from backend.config import settings


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram Web App initData HMAC-SHA256 signature.
    Returns parsed user data if valid, raises ValueError otherwise.
    """
    parsed = parse_qs(init_data)

    if "hash" not in parsed:
        raise ValueError("Missing hash in initData")

    received_hash = parsed.pop("hash")[0]

    # Build data-check-string: sorted key=value pairs joined by newline
    data_check_pairs = []
    for key in sorted(parsed.keys()):
        value = unquote(parsed[key][0])
        data_check_pairs.append(f"{key}={value}")
    data_check_string = "\n".join(data_check_pairs)

    # HMAC secret = HMAC_SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid initData hash")

    return {k: v[0] for k, v in parsed.items()}


async def verify_bearer_token(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: verify Bearer token from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization[7:]
    if token != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return token


async def verify_telegram_webapp(
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    """FastAPI dependency: validate Telegram WebApp initData from header."""
    if not x_telegram_init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-Init-Data header",
        )
    try:
        return verify_telegram_init_data(x_telegram_init_data, settings.BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
