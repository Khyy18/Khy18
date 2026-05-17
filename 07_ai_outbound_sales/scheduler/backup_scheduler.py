"""Backup scheduler - runs periodic database and Redis backups."""
from __future__ import annotations

import logging
from typing import Any

from core.backup import BackupManager

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Schedules and manages backup operations."""

    def __init__(
        self,
        database_url: str,
        redis_url: str,
        backup_dir: str = "/backups",
        settings: Any = None,
    ) -> None:
        """Initialize BackupScheduler.

        Args:
            database_url: PostgreSQL connection URL.
            redis_url: Redis connection URL.
            backup_dir: Directory to store backup files.
            settings: Application settings (for Telegram alerts, S3 config).
        """
        self._backup_manager = BackupManager(
            database_url=database_url,
            redis_url=redis_url,
            backup_dir=backup_dir,
        )
        self._settings = settings

    async def run_backup_tick(self) -> dict[str, Any]:
        """Run one backup cycle: pg_dump + verify + rotate + Redis snapshot.

        Returns:
            Dict with results from each step.
        """
        result: dict[str, Any] = {
            "pg_dump": None,
            "verified": False,
            "rotation": None,
            "redis_snapshot": False,
        }

        # Step 1: Run pg_dump
        dump_result = await self._backup_manager.run_pg_dump()
        result["pg_dump"] = dump_result

        if not dump_result["success"]:
            # Alert on failure
            if self._settings:
                token = getattr(self._settings, "telegram_bot_token", "")
                chat_id = getattr(self._settings, "telegram_chat_id", "")
                await self._backup_manager.alert_on_failure(
                    error_msg=f"pg_dump failed for backup at {dump_result['file_path']}",
                    telegram_bot_token=token,
                    telegram_chat_id=chat_id,
                )
            return result

        # Step 2: Verify the backup
        verified = await self._backup_manager.verify_backup(dump_result["file_path"])
        result["verified"] = verified

        if not verified:
            if self._settings:
                token = getattr(self._settings, "telegram_bot_token", "")
                chat_id = getattr(self._settings, "telegram_chat_id", "")
                await self._backup_manager.alert_on_failure(
                    error_msg=f"Backup verification failed for {dump_result['file_path']}",
                    telegram_bot_token=token,
                    telegram_chat_id=chat_id,
                )
            return result

        # Step 3: Rotate old backups
        rotation_result = await self._backup_manager.rotate_backups()
        result["rotation"] = rotation_result

        # Step 4: Trigger Redis snapshot
        redis_ok = await self._backup_manager.trigger_redis_snapshot()
        result["redis_snapshot"] = redis_ok

        logger.info("Backup tick completed: %s", result)
        return result

    async def run_redis_snapshot_tick(self) -> bool:
        """Run Redis BGSAVE snapshot (called more frequently than full backup).

        Returns:
            True if BGSAVE succeeded.
        """
        return await self._backup_manager.trigger_redis_snapshot()
