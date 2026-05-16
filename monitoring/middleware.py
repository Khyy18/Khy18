"""aiohttp middleware для автоматического сбора HTTP-метрик."""

from __future__ import annotations

import time

from aiohttp import web

from monitoring.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL


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
        path = request.path
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duration)
    return response
