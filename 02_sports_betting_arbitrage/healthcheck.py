"""HTTP healthcheck endpoint for the arbitrage bot.

Provides /healthz endpoint returning bot status as JSON.
Returns 200 if healthy, 503 if degraded.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthcheckServer:
    """Минимальный HTTP-сервер для /healthz endpoint."""

    def __init__(self, state: dict[str, Any], port: int = 8080) -> None:
        self._state = state
        self._port = int(os.getenv("ARB_HEALTHCHECK_PORT", str(port)))
        self._start_time = time.time()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Запустить HTTP-сервер (aiohttp.web.AppRunner)."""
        self._app = web.Application()
        self._app.router.add_get("/healthz", self._handle_healthz)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("Healthcheck сервер запущен на порту %d", self._port)

    async def stop(self) -> None:
        """Остановить HTTP-сервер."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Healthcheck сервер остановлен")

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        """Обработчик GET /healthz."""
        scanner_active = self._state.get("scanner_active", False)
        last_scan_ts = self._state.get("last_scan_ts", "")
        uptime_sec = int(time.time() - self._start_time)

        # Determine health
        healthy = True
        if last_scan_ts:
            try:
                last_dt = datetime.fromisoformat(last_scan_ts.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed > 300:  # 5 minutes
                    healthy = False
            except (ValueError, TypeError):
                pass

        # scanner_active=False due to error (not manual stop) means unhealthy
        if not scanner_active and self._state.get("scanner_stopped_by_error", False):
            healthy = False

        body = json.dumps({
            "status": "ok" if healthy else "degraded",
            "scanner_active": scanner_active,
            "last_scan_ts": last_scan_ts,
            "uptime_sec": uptime_sec,
        })

        status_code = 200 if healthy else 503
        return web.Response(text=body, content_type="application/json", status=status_code)
