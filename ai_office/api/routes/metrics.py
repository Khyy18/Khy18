"""Эндпоинт для Prometheus-совместимых метрик."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ai_office.api.observability import metrics_collector
from ai_office.core.memory import agent_memory

router = APIRouter(tags=["metrics"])


@router.get(
    "/api/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics",
)
async def get_metrics():
    """Получить метрики в формате Prometheus text exposition."""
    # Update memory stats gauges before formatting
    stats = agent_memory.get_stats()
    for agent_name, count in stats["entries_per_agent"].items():
        await metrics_collector.set_gauge(
            "ai_office_memory_entries",
            float(count),
            labels={"agent_name": agent_name},
        )

    content = await metrics_collector.format_prometheus()
    return PlainTextResponse(
        content=content,
        media_type="text/plain; version=0.0.4",
    )
