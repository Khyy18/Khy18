"""Эндпоинт для Prometheus-совместимых метрик."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ai_office.api.observability import metrics_collector

router = APIRouter(tags=["metrics"])


@router.get(
    "/api/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics",
)
async def get_metrics():
    """Получить метрики в формате Prometheus text exposition."""
    content = await metrics_collector.format_prometheus()
    return PlainTextResponse(
        content=content,
        media_type="text/plain; version=0.0.4",
    )
