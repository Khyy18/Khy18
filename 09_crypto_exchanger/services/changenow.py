"""ChangeNOW API v2 client."""

import logging
from typing import Any, Optional

import aiohttp

from config import config

logger = logging.getLogger(__name__)

BASE_URL = config.CHANGENOW_BASE_URL
API_KEY = config.CHANGENOW_API_KEY
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Shared session for connection pooling
_session: Optional[aiohttp.ClientSession] = None


class ChangeNowError(Exception):
    """ChangeNOW API error."""

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
    """Make an API request to ChangeNOW."""
    url = f"{BASE_URL}{path}"
    headers = {"x-changenow-api-key": API_KEY}

    try:
        session = _get_session()
        async with session.request(
            method, url, params=params, json=json, headers=headers
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            error_text = await resp.text()
            logger.error(
                "ChangeNOW API error: %s %s -> %d: %s",
                method, path, resp.status, error_text,
            )
            raise ChangeNowError(
                f"API error {resp.status}: {error_text}"
            )
    except aiohttp.ClientError as e:
        logger.error("ChangeNOW connection error: %s", e)
        raise ChangeNowError(f"Connection error: {e}") from e


async def get_currencies() -> list[dict[str, Any]]:
    """Get list of available currencies."""
    return await _request("GET", "/exchange/currencies", params={"active": "true"})


async def get_estimated_amount(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    flow: str = "standard",
) -> dict[str, Any]:
    """Get estimated exchange amount.

    Args:
        from_currency: Source currency ticker.
        to_currency: Target currency ticker.
        from_amount: Amount to exchange.
        flow: 'standard' or 'fixed-rate'.

    Returns:
        Dict with toAmount, rateId (for fixed-rate), etc.
    """
    params: dict[str, Any] = {
        "fromCurrency": from_currency.lower(),
        "toCurrency": to_currency.lower(),
        "fromAmount": str(from_amount),
        "type": "direct",
    }
    if flow == "fixed-rate":
        params["flow"] = "fixed-rate"

    return await _request("GET", "/exchange/estimated-amount", params=params)


async def get_range(
    from_currency: str, to_currency: str
) -> dict[str, Any]:
    """Get min/max exchange amounts."""
    params = {
        "fromCurrency": from_currency.lower(),
        "toCurrency": to_currency.lower(),
    }
    return await _request("GET", "/exchange/range", params=params)


async def create_exchange(
    from_currency: str,
    to_currency: str,
    from_amount: float,
    address: str,
    flow: str = "standard",
    rate_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new exchange.

    Args:
        from_currency: Source currency ticker.
        to_currency: Target currency ticker.
        from_amount: Amount to exchange.
        address: Payout wallet address.
        flow: 'standard' or 'fixed-rate'.
        rate_id: Required for fixed-rate exchanges.

    Returns:
        Dict with id, payinAddress, payoutAddress, etc.
    """
    body: dict[str, Any] = {
        "fromCurrency": from_currency.lower(),
        "toCurrency": to_currency.lower(),
        "fromAmount": str(from_amount),
        "address": address,
        "flow": flow,
        "type": "direct",
    }
    if rate_id:
        body["rateId"] = rate_id

    return await _request("POST", "/exchange", json=body)


async def get_exchange_status(exchange_id: str) -> dict[str, Any]:
    """Get exchange status by ID."""
    return await _request(
        "GET",
        f"/exchange/by-id/{exchange_id}",
        params={"apiKey": API_KEY},
    )
