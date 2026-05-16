"""Health Monitor - self-monitoring system with auto-recovery."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from integrations.notifications import send_telegram_notification

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Result of a health check run."""

    database_ok: bool = False
    redis_ok: bool = False
    disk_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    issues: list[str] = field(default_factory=list)
    timestamp: str = ""

    @property
    def all_healthy(self) -> bool:
        """Return True if all checks passed and no critical issues."""
        return (
            self.database_ok
            and self.redis_ok
            and self.disk_usage_percent < 90.0
            and len(self.issues) == 0
        )


class HealthMonitor:
    """Monitors system health and triggers alerts/auto-recovery."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def run_health_checks(self) -> HealthReport:
        """Run all health checks and return a report."""
        report = HealthReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        report.database_ok = await self._check_database()
        report.redis_ok = await self._check_redis()
        report.disk_usage_percent = self._check_disk_space()
        report.memory_usage_percent = self._check_memory()

        # Populate issues
        if not report.database_ok:
            report.issues.append("Database connection failed")
        if not report.redis_ok:
            report.issues.append("Redis connection failed")
        if report.disk_usage_percent >= 90.0:
            report.issues.append(
                f"Disk usage critical: {report.disk_usage_percent:.1f}%"
            )

        await self._auto_recover(report)

        return report

    async def _check_database(self) -> bool:
        """Attempt a simple database query to verify connectivity."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error("Database health check failed: %s", exc)
            return False

    async def _check_redis(self) -> bool:
        """Attempt a Redis ping to verify connectivity."""
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self._settings.redis_url)
            try:
                await client.ping()
                return True
            finally:
                await client.close()
        except Exception as exc:
            logger.error("Redis health check failed: %s", exc)
            return False

    def _check_disk_space(self) -> float:
        """Check disk usage percentage using os.statvfs."""
        try:
            stat = os.statvfs("/")
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            if total == 0:
                return 0.0
            used_percent = ((total - free) / total) * 100
            return round(used_percent, 1)
        except (OSError, AttributeError):
            # statvfs not available on all platforms (e.g. Windows)
            return 0.0

    def _check_memory(self) -> float:
        """Check memory usage from /proc/meminfo if available."""
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()

            mem_info: dict[str, int] = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    value = int(parts[1])  # in kB
                    mem_info[key] = value

            total = mem_info.get("MemTotal", 0)
            available = mem_info.get("MemAvailable", 0)

            if total == 0:
                return 0.0

            used_percent = ((total - available) / total) * 100
            return round(used_percent, 1)
        except (OSError, ValueError, KeyError):
            return 0.0

    async def _auto_recover(self, report: HealthReport) -> None:
        """Attempt auto-recovery actions based on health report."""
        if report.disk_usage_percent >= 90.0:
            logger.warning(
                "Disk usage at %.1f%% - cleanup needed. "
                "Consider removing old logs and temporary files.",
                report.disk_usage_percent,
            )

        if report.issues:
            logger.critical(
                "Health check detected %d issue(s): %s",
                len(report.issues),
                "; ".join(report.issues),
            )

    async def send_health_report(self, report: HealthReport) -> None:
        """Format and send a health report via Telegram if configured."""
        if not self._settings.health_telegram_alerts:
            return

        status = "HEALTHY" if report.all_healthy else "UNHEALTHY"
        text_msg = (
            f"*Health Report - {status}*\n\n"
            f"Database: {'OK' if report.database_ok else 'FAIL'}\n"
            f"Redis: {'OK' if report.redis_ok else 'FAIL'}\n"
            f"Disk: {report.disk_usage_percent:.1f}%\n"
            f"Memory: {report.memory_usage_percent:.1f}%\n"
            f"Timestamp: {report.timestamp}"
        )

        if report.issues:
            text_msg += f"\n\nIssues:\n" + "\n".join(
                f"- {issue}" for issue in report.issues
            )

        await send_telegram_notification(
            bot_token=self._settings.telegram_bot_token,
            chat_id=self._settings.telegram_chat_id,
            text=text_msg,
        )

    async def send_critical_alert(self, issue: str) -> None:
        """Send an immediate critical alert via Telegram."""
        text_msg = f"*CRITICAL ALERT*\n\n{issue}"
        await send_telegram_notification(
            bot_token=self._settings.telegram_bot_token,
            chat_id=self._settings.telegram_chat_id,
            text=text_msg,
        )
