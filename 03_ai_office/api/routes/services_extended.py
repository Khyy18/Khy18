"""API роуты для дополнительных внешних сервисов (Zenith, Text Agency, Combo Bot)."""

from fastapi import APIRouter
import httpx

from ai_office.core.config import settings

router = APIRouter(prefix="/api/services", tags=["services"])

# Module-level httpx client with connection pooling. This client lives for the
# process lifetime and is never explicitly closed, matching the pattern in
# services.py. In a long-running FastAPI process this is intentional: it avoids
# per-request TCP+TLS handshake overhead and the client is cleaned up when the
# process exits.
_http_client = httpx.AsyncClient(timeout=5.0)


@router.get("/zenith")
async def zenith_status():
    """Проверка статуса и получение метрик сервиса Zenith Crypto Trading."""
    base_url = settings.zenith_api_url
    result = {
        "service": "zenith_trading",
        "status": "offline",
        "health": None,
        "stats": None,
    }

    try:
        health_resp = await _http_client.get(f"{base_url}/health")
        if health_resp.status_code == 200:
            result["status"] = "online"
            result["health"] = health_resp.json()

        try:
            stats_resp = await _http_client.get(f"{base_url}/api/stats")
            if stats_resp.status_code == 200:
                result["stats"] = stats_resp.json()
        except httpx.HTTPError:
            pass

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        result["status"] = "offline"

    return result


@router.get("/text-agency")
async def text_agency_status():
    """Проверка статуса и получение метрик сервиса AI Text Agency."""
    base_url = settings.text_agency_api_url
    result = {
        "service": "text_agency",
        "status": "offline",
        "health": None,
        "stats": None,
    }

    try:
        health_resp = await _http_client.get(f"{base_url}/health")
        if health_resp.status_code == 200:
            result["status"] = "online"
            result["health"] = health_resp.json()

        try:
            stats_resp = await _http_client.get(f"{base_url}/api/stats")
            if stats_resp.status_code == 200:
                result["stats"] = stats_resp.json()
        except httpx.HTTPError:
            pass

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        result["status"] = "offline"

    return result


@router.get("/combo-bot")
async def combo_bot_status():
    """Проверка статуса и получение метрик сервиса Combo Bot."""
    base_url = settings.combo_bot_api_url
    result = {
        "service": "combo_bot",
        "status": "offline",
        "health": None,
        "stats": None,
    }

    try:
        health_resp = await _http_client.get(f"{base_url}/health")
        if health_resp.status_code == 200:
            result["status"] = "online"
            result["health"] = health_resp.json()

        try:
            stats_resp = await _http_client.get(f"{base_url}/api/status")
            if stats_resp.status_code == 200:
                result["stats"] = stats_resp.json()
        except httpx.HTTPError:
            pass

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        result["status"] = "offline"

    return result
