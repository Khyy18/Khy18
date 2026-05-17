"""Automated data backup system for PostgreSQL and Redis."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages automated PostgreSQL backups and Redis snapshots."""

    def __init__(
        self,
        database_url: str,
        redis_url: str,
        backup_dir: str = "/backups",
        retention_days: int = 7,
    ) -> None:
        """Initialize BackupManager.

        Args:
            database_url: PostgreSQL connection URL.
            redis_url: Redis connection URL.
            backup_dir: Directory to store backup files.
            retention_days: Number of days to retain backups.
        """
        self._database_url = database_url
        self._redis_url = redis_url
        self._backup_dir = backup_dir
        self._retention_days = retention_days
        self._max_files = retention_days * 4  # 4 backups per day (every 6 hours)

    def _parse_database_url(self) -> dict[str, str]:
        """Parse database URL into components for pg_dump.

        Returns:
            Dict with host, port, user, password, dbname.
        """
        # Handle asyncpg URL format: postgresql+asyncpg://user:pass@host:port/dbname
        url = self._database_url.replace("postgresql+asyncpg://", "postgresql://")
        parsed = urlparse(url)
        return {
            "host": parsed.hostname or "localhost",
            "port": str(parsed.port or 5432),
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
            "dbname": parsed.path.lstrip("/") or "postgres",
        }

    async def run_pg_dump(self) -> dict[str, Any]:
        """Run pg_dump via asyncio subprocess.

        Returns:
            Dict with success, file_path, size_bytes, duration_seconds.
        """
        start_time = datetime.now(timezone.utc)
        db_params = self._parse_database_url()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        dbname = db_params["dbname"]
        output_filename = f"backup_{dbname}_{timestamp}.dump"
        output_path = os.path.join(self._backup_dir, output_filename)

        # Ensure backup directory exists
        os.makedirs(self._backup_dir, exist_ok=True)

        env = os.environ.copy()
        env["PGPASSWORD"] = db_params["password"]

        cmd = [
            "pg_dump",
            "--no-owner",
            "--format=custom",
            "--compress=9",
            f"--host={db_params['host']}",
            f"--port={db_params['port']}",
            f"--username={db_params['user']}",
            f"--file={output_path}",
            dbname,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            if process.returncode == 0:
                size_bytes = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                logger.info(
                    "pg_dump completed: file=%s size=%d duration=%.2fs",
                    output_path,
                    size_bytes,
                    duration,
                )
                return {
                    "success": True,
                    "file_path": output_path,
                    "size_bytes": size_bytes,
                    "duration_seconds": duration,
                }
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error("pg_dump failed (rc=%d): %s", process.returncode, error_msg)
                return {
                    "success": False,
                    "file_path": output_path,
                    "size_bytes": 0,
                    "duration_seconds": duration,
                }
        except Exception as exc:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error("pg_dump exception: %s", exc)
            return {
                "success": False,
                "file_path": output_path,
                "size_bytes": 0,
                "duration_seconds": duration,
            }

    async def rotate_backups(self) -> dict[str, Any]:
        """Rotate old backup files, keeping at most max_files (28 by default).

        Returns:
            Dict with deleted_count and remaining_count.
        """
        backup_path = Path(self._backup_dir)
        if not backup_path.exists():
            return {"deleted_count": 0, "remaining_count": 0}

        dump_files = sorted(
            backup_path.glob("*.dump"),
            key=lambda f: f.stat().st_mtime,
        )

        deleted_count = 0
        if len(dump_files) > self._max_files:
            files_to_delete = dump_files[: len(dump_files) - self._max_files]
            for f in files_to_delete:
                try:
                    f.unlink()
                    deleted_count += 1
                    logger.info("Deleted old backup: %s", f.name)
                except OSError as exc:
                    logger.error("Failed to delete backup %s: %s", f.name, exc)

        remaining = len(dump_files) - deleted_count
        logger.info(
            "Backup rotation complete: deleted=%d remaining=%d",
            deleted_count,
            remaining,
        )
        return {"deleted_count": deleted_count, "remaining_count": remaining}

    async def verify_backup(self, file_path: str) -> bool:
        """Verify a backup file exists and has a reasonable size.

        Args:
            file_path: Path to the backup file to verify.

        Returns:
            True if the file exists and is larger than 1024 bytes.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("Backup verification failed: file not found %s", file_path)
            return False
        size = path.stat().st_size
        if size <= 1024:
            logger.warning(
                "Backup verification failed: file too small (%d bytes) %s",
                size,
                file_path,
            )
            return False
        return True

    async def trigger_redis_snapshot(self) -> bool:
        """Trigger a Redis BGSAVE snapshot.

        Returns:
            True if BGSAVE command was sent successfully.
        """
        try:
            client = aioredis.from_url(self._redis_url)
            try:
                await client.bgsave()
                logger.info("Redis BGSAVE triggered successfully")
                return True
            finally:
                await client.close()
        except Exception as exc:
            logger.error("Redis BGSAVE failed: %s", exc)
            return False

    async def upload_to_s3(
        self,
        file_path: str,
        s3_config: dict[str, str] | None,
    ) -> bool:
        """Upload a backup file to S3-compatible storage.

        Args:
            file_path: Path to the file to upload.
            s3_config: Dict with endpoint, bucket, access_key, secret_key.
                       If empty or None, skip upload.

        Returns:
            True if upload succeeded, False otherwise.
        """
        if not s3_config or not s3_config.get("endpoint"):
            logger.debug("S3 config not provided, skipping upload")
            return False

        endpoint = s3_config["endpoint"]
        bucket = s3_config.get("bucket", "backups")
        access_key = s3_config.get("access_key", "")
        secret_key = s3_config.get("secret_key", "")
        filename = os.path.basename(file_path)

        url = f"{endpoint}/{bucket}/{filename}"

        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, "rb") as f:
                    data = f.read()
                headers = {
                    "Content-Type": "application/octet-stream",
                }
                if access_key:
                    headers["Authorization"] = f"AWS {access_key}:{secret_key}"

                async with session.put(url, data=data, headers=headers) as resp:
                    if resp.status in (200, 201):
                        logger.info("Uploaded backup to S3: %s", url)
                        return True
                    else:
                        logger.error(
                            "S3 upload failed (status=%d): %s",
                            resp.status,
                            await resp.text(),
                        )
                        return False
        except Exception as exc:
            logger.error("S3 upload exception: %s", exc)
            return False

    async def alert_on_failure(
        self,
        error_msg: str,
        telegram_bot_token: str,
        telegram_chat_id: str,
    ) -> None:
        """Send a Telegram alert about backup failure.

        Args:
            error_msg: Description of the failure.
            telegram_bot_token: Telegram bot API token.
            telegram_chat_id: Telegram chat ID to send alert to.
        """
        if not telegram_bot_token or not telegram_chat_id:
            logger.warning("Telegram credentials not configured, cannot send alert")
            return

        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": f"[BACKUP ALERT] {error_msg}",
            "parse_mode": "HTML",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("Backup failure alert sent to Telegram")
                    else:
                        logger.error(
                            "Failed to send Telegram alert (status=%d)",
                            resp.status,
                        )
        except Exception as exc:
            logger.error("Telegram alert exception: %s", exc)
