"""Планировщик бэкапов через ARQ.

Задача backup_task выполняет BackupService.run_backup().
Рекомендуется добавить в WorkerSettings.cron_jobs для запуска по расписанию:

    from arq.cron import cron
    cron_jobs = [cron(backup_task, hour=BACKUP_SCHEDULE_HOUR, minute=0)]
"""

from __future__ import annotations

from typing import Any

from logging_config import get_logger

log = get_logger(__name__)


async def backup_task(ctx: dict[str, Any]) -> str:
    """ARQ-задача выполнения бэкапа."""
    from backup.backup import BackupService

    service = BackupService()
    success = await service.run_backup()

    if success:
        log.info("backup_task_completed")
        return "backup_completed"
    else:
        log.error("backup_task_failed")
        return "backup_failed"
