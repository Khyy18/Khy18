"""Telegram initData HMAC-SHA256 validation."""

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs, unquote

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str) -> str:
    """Validate Telegram initData using HMAC-SHA256.

    Follows Telegram's documented algorithm:
    1. Parse the init_data query string.
    2. Remove the 'hash' parameter.
    3. Sort remaining parameters alphabetically.
    4. Build data-check-string as "key=value\\n..." pairs.
    5. Compute HMAC-SHA256 of data-check-string using
       SHA256(bot_token) as the secret key.
    6. Compare computed hash with the provided hash.

    Returns the user_id extracted from the validated data.
    Raises HTTPException(403) if validation fails.
    """
    if not settings.telegram_bot_token:
        logger.warning(
            "TELEGRAM_BOT_TOKEN not configured, skipping initData validation"
        )
        # In development mode, try to extract user_id anyway
        parsed = parse_qs(init_data)
        user_data = parsed.get("user", [None])[0]
        if user_data:
            user_obj = json.loads(unquote(user_data))
            return str(user_obj.get("id", "dev_user"))
        return "dev_user"

    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]

    if not received_hash:
        raise HTTPException(status_code=403, detail="Missing hash in initData")

    # Build data-check-string: sort params alphabetically, join with \n
    data_check_pairs = []
    for key in sorted(parsed.keys()):
        # parse_qs returns lists, take first value
        value = parsed[key][0]
        data_check_pairs.append(f"{key}={value}")
    data_check_string = "\n".join(data_check_pairs)

    # Compute secret key: HMAC-SHA256 of bot token with "WebAppData" as key
    secret_key = hmac.HMAC(
        b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256
    ).digest()

    # Compute hash of data-check-string
    computed_hash = hmac.HMAC(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=403, detail="Invalid initData signature")

    # Extract user_id from validated data
    user_data = parsed.get("user", [None])[0]
    if user_data:
        user_obj = json.loads(unquote(user_data))
        return str(user_obj.get("id", ""))

    raise HTTPException(status_code=403, detail="No user data in initData")


async def get_telegram_user(
    x_telegram_init_data: str = Header(default=""),
) -> str:
    """FastAPI dependency that validates Telegram initData from header.

    Returns the validated user_id.
    If no initData is provided and bot token is not configured, returns empty string.
    """
    if not x_telegram_init_data:
        if not settings.telegram_bot_token:
            logger.warning("No initData provided, dev mode - skipping validation")
            return ""
        raise HTTPException(
            status_code=403, detail="X-Telegram-Init-Data header required"
        )
    return validate_init_data(x_telegram_init_data)
