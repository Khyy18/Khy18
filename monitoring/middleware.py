"""aiohttp middleware для автоматического сбора HTTP-метрик."""

from __future__ import annotations

import time

from aiohttp import web

from monitoring.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

# Набор известных путей. Любой путь не из этого набора нормализуется в "/__other"
# для предотвращения cardinality explosion от бот-сканеров.
_KNOWN_PATHS: set[str] = {
    "/webhook/telegram",
    "/health",
    "/metrics",
    "/api/payment",
    "/api/plans",
    "/api/subscription",
}


def _normalize_path(path: str) -> str:
    """Нормализовать путь для метрик. Неизвестные пути -> /__other."""
    if path in _KNOWN_PATHS:
        return path
    # Проверяем префиксы для путей с параметрами
    for known in _KNOWN_PATHS:
        if path.startswith(known + "/"):
            return known
    return "/__other"


@web.middleware
async def metrics_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Middleware: считает запросы и измеряет длительность."""
    start = time.perf_counter()
    try:
        response = await handler(request)
        status = str(response.status)
    except web.HTTPException as exc:
        status = str(exc.status)
        raise
    except Exception:
        status = "500"
        raise
    finally:
        duration = time.perf_counter() - start
        method = request.method
        path = _normalize_path(request.path)
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duration)
    return response
