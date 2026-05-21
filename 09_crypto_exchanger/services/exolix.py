"""Exolix API client (fallback provider)."""

import logging
from typing import Any, Optional

import aiohttp

from config import config

logger = logging.getLogger(__name__)

BASE_URL = config.EXOLIX_BASE_URL
API_KEY = config.EXOLIX_API_KEY
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Shared session for connection pooling
_session: Optional[aiohttp.ClientSession] = None


class ExolixError(Exception):
    """Exolix API error."""

    pass


def _get_session() -> aiohttp.ClientSession:
    """Get or create the shared aiohttp session."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=TIMEOUT)
    return _session


async def close_session() -> None:
    """Close the shared aiohttp session. Call on shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def _request(
    method: str, path: str, params: Optional[dict] = None, json: Optional[dict] = None
) -> Any:
    """Make an API request to Exolix."""
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        session = _get_session()
        async with session.request(
            method, url, params=params, json=json, headers=headers
        ) as resp:
            if resp.status in (200, 201):
                return await resp.json()
            error_text = await resp.text()
            logger.error(
                "Exolix API error: %s %s -> %d: %s",
                method, path, resp.status, error_text,
            )
            raise ExolixError(f"API error {resp.status}: {error_text}")
    except aiohttp.ClientError as e:
        logger.error("Exolix connection error: %s", e)
        raise ExolixError(f"Connection error: {e}") from e


async def get_currencies() -> list[dict[str, Any]]:
    """Get list of available currencies."""
    data = await _request("GET", "/currencies")
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data if isinstance(data, list) else []


async def get_estimated_amount(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    rate_type: str = "fixed",
) -> dict[str, Any]:
    """Get estimated exchange amount.

    Args:
        from_currency: Source currency ticker.
        to_currency: Target currency ticker.
        from_amount: Amount to exchange.
        rate_type: 'fixed' or 'float'.

    Returns:
        Dict with toAmount, rate, etc.
    """
    params = {
        "coinFrom": from_currency.upper(),
        "coinTo": to_currency.upper(),
        "amount": str(from_amount),
        "rateType": rate_type,
    }
    return await _request("GET", "/rate", params=params)


async def create_exchange(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    address: str,
    rate_type: str = "fixed",
) -> dict[str, Any]:
    """Create a new exchange.

    Args:
        from_currency: Source currency ticker.
        to_currency: Target currency ticker.
        from_amount: Amount to exchange.
        address: Payout wallet address.
        rate_type: 'fixed' or 'float'.

    Returns:
        Dict with id, depositAddress, etc.
    """
    body = {
        "coinFrom": from_currency.upper(),
        "coinTo": to_currency.upper(),
        "amount": from_amount,
        "withdrawalAddress": address,
        "rateType": rate_type,
    }
    return await _request("POST", "/transactions", json=body)


async def get_exchange_status(exchange_id: str) -> dict[str, Any]:
    """Get exchange status by ID."""
    return await _request("GET", f"/transactions/{exchange_id}")
