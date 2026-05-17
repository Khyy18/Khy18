"""API роуты для внешних сервисов (Outbound Sales и др.)."""

from fastapi import APIRouter
import httpx

from ai_office.core.config import settings

router = APIRouter(prefix="/api/services", tags=["services"])


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
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check service health
            health_resp = await client.get(f"{base_url}/health")
            if health_resp.status_code == 200:
                result["status"] = "online"
                result["health"] = health_resp.json()

            # Fetch funnel analytics
            try:
                stats_resp = await client.get(f"{base_url}/api/analytics/funnel")
                if stats_resp.status_code == 200:
                    result["stats"] = stats_resp.json()
            except httpx.HTTPError:
                pass

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        result["status"] = "offline"

    return result
