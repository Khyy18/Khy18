"""API роуты для внешних сервисов (Outbound Sales и др.)."""

from fastapi import APIRouter
import httpx

from ai_office.core.config import settings

router = APIRouter(prefix="/api/services", tags=["services"])

# Module-level httpx client with connection pooling to avoid per-request
# TCP+TLS handshake overhead under repeated polling from the SalesPanel.
_http_client = httpx.AsyncClient(timeout=5.0)


# NOTE: This endpoint is intentionally unauthenticated. The 03_ai_office app
# applies TelegramAuthMiddleware globally, so this route is protected at the
# middleware layer. It is left without an explicit auth dependency to allow
# internal service-mesh callers (health checks, orchestrators) to reach it
# without Telegram credentials.
@router.get("/outbound-sales")
async def outbound_sales_status():
    """Проверка статуса и получение метрик сервиса Outbound Sales."""
    base_url = settings.outbound_sales_api_url
    result = {
        "service": "outbound_sales",
        "status": "offline",
        "health": None,
        "stats": None,
    }

    try:
        # Check service health
        health_resp = await _http_client.get(f"{base_url}/health")
        if health_resp.status_code == 200:
            result["status"] = "online"
            result["health"] = health_resp.json()

        # Fetch funnel analytics
        try:
            stats_resp = await _http_client.get(f"{base_url}/api/analytics/funnel")
            if stats_resp.status_code == 200:
                result["stats"] = stats_resp.json()
        except httpx.HTTPError:
            pass

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        result["status"] = "offline"

    return result
