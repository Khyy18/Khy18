"""Exchange router: facade over ChangeNOW (primary) and Exolix (fallback).

Applies MARKUP_PERCENT to all estimated amounts.
"""

import logging
from typing import Any, Optional

from config import config
from services import changenow, exolix
from services.changenow import ChangeNowError
from services.exolix import ExolixError
from services.rate_cache import rate_cache

logger = logging.getLogger(__name__)


def _apply_markup(estimated_amount: float) -> tuple[float, float]:
    """Apply markup and return (amount_after_markup, markup_amount).

    Markup reduces the amount the user receives.
    """
    markup = estimated_amount * (config.MARKUP_PERCENT / 100)
    return estimated_amount - markup, markup


async def get_currencies() -> list[dict[str, Any]]:
    """Get available currencies. Tries ChangeNOW first, then Exolix."""
    try:
        return await changenow.get_currencies()
    except ChangeNowError:
        logger.warning("ChangeNOW currencies failed, trying Exolix")
        try:
            return await exolix.get_currencies()
        except ExolixError:
            logger.error("Both providers failed for currencies")
            raise


async def get_estimate(
    from_currency: str,
    to_currency: str,
    amount: float,
    flow: str = "standard",
) -> dict[str, Any]:
    """Get exchange estimate with markup applied.

    Returns:
        Dict with keys: toAmount, markupAmount, provider, rateId (optional).
    """
    # Check cache first
    cached = rate_cache.get(from_currency, to_currency, amount, flow)
    if cached:
        return cached

    result = await _get_estimate_from_providers(from_currency, to_currency, amount, flow)

    # Cache the result
    rate_cache.set(from_currency, to_currency, amount, flow, result)
    return result


async def _get_estimate_from_providers(
    from_currency: str,
    to_currency: str,
    amount: float,
    flow: str,
) -> dict[str, Any]:
    """Try ChangeNOW then Exolix for estimates."""
    # Try ChangeNOW first
    try:
        data = await changenow.get_estimated_amount(
            from_currency, to_currency, amount, flow
        )
        raw_amount = float(data.get("toAmount", 0))
        final_amount, markup = _apply_markup(raw_amount)
        result: dict[str, Any] = {
            "toAmount": final_amount,
            "rawAmount": raw_amount,
            "markupAmount": markup,
            "provider": "changenow",
        }
        if "rateId" in data:
            result["rateId"] = data["rateId"]
        return result
    except ChangeNowError:
        logger.warning("ChangeNOW estimate failed, trying Exolix")

    # Fallback to Exolix
    try:
        rate_type = "fixed" if flow == "fixed-rate" else "float"
        data = await exolix.get_estimated_amount(
            from_currency, to_currency, amount, rate_type
        )
        raw_amount = float(data.get("toAmount", 0))
        final_amount, markup = _apply_markup(raw_amount)
        return {
            "toAmount": final_amount,
            "rawAmount": raw_amount,
            "markupAmount": markup,
            "provider": "exolix",
        }
    except ExolixError:
        logger.error("Both providers failed for estimate")
        raise


async def get_range(
    from_currency: str, to_currency: str
) -> dict[str, Any]:
    """Get min/max exchange amounts."""
    try:
        return await changenow.get_range(from_currency, to_currency)
    except ChangeNowError:
        logger.warning("ChangeNOW range failed, returning defaults")
        return {"minAmount": None, "maxAmount": None}


async def create_exchange(
    from_currency: str,
    to_currency: str,
    amount: float,
    address: str,
    flow: str = "standard",
    rate_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict[str, Any]:
    """Create exchange. Tries specified provider or ChangeNOW first with Exolix fallback.

    Returns:
        Dict with keys: id, depositAddress, provider, status.
    """
    if provider != "exolix":
        try:
            data = await changenow.create_exchange(
                from_currency, to_currency, amount, address, flow, rate_id
            )
            return {
                "id": data.get("id"),
                "depositAddress": data.get("payinAddress"),
                "provider": "changenow",
                "status": data.get("status", "waiting"),
            }
        except ChangeNowError:
            logger.warning("ChangeNOW create failed, trying Exolix")

    # Fallback to Exolix
    try:
        rate_type = "fixed" if flow == "fixed-rate" else "float"
        data = await exolix.create_exchange(
            from_currency, to_currency, amount, address, rate_type
        )
        return {
            "id": str(data.get("id")),
            "depositAddress": data.get("depositAddress"),
            "provider": "exolix",
            "status": data.get("status", "waiting"),
        }
    except ExolixError:
        logger.error("Both providers failed to create exchange")
        raise


async def get_status(exchange_id: str, provider: str) -> dict[str, Any]:
    """Get exchange status from the specified provider.

    Returns:
        Dict with normalized status field.
    """
    if provider == "changenow":
        data = await changenow.get_exchange_status(exchange_id)
        return {
            "status": data.get("status", "unknown"),
            "hash": data.get("payoutHash"),
            "raw": data,
        }
    elif provider == "exolix":
        data = await exolix.get_exchange_status(exchange_id)
        return {
            "status": _normalize_exolix_status(data.get("status", "unknown")),
            "hash": data.get("hashOut", {}).get("hash") if isinstance(data.get("hashOut"), dict) else None,
            "raw": data,
        }
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _normalize_exolix_status(status: str) -> str:
    """Normalize Exolix status to ChangeNOW-compatible status."""
    mapping = {
        "wait": "waiting",
        "confirmation": "confirming",
        "exchanging": "exchanging",
        "sending": "sending",
        "success": "finished",
        "overdue": "failed",
        "refund": "refunded",
    }
    return mapping.get(status, status)
