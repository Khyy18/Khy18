"""Endpoint /metrics для Prometheus scraping."""

from __future__ import annotations

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


async def metrics_handler(request: web.Request) -> web.Response:
    """Обработчик GET /metrics - возвращает метрики в формате Prometheus."""
    body = generate_latest()
    return web.Response(
        body=body,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


def setup_metrics_endpoint(app: web.Application) -> None:
    """Добавить /metrics route к aiohttp-приложению."""
    app.router.add_get("/metrics", metrics_handler)
