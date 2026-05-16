"""Сервис бэкапов: PostgreSQL (pg_dump), SQLite (copy), S3 upload.

Поддерживает:
  - PostgreSQL: через asyncio subprocess (pg_dump).
  - SQLite: безопасное копирование через sqlite3.Connection.backup().
  - Загрузка в S3-совместимое хранилище через aiohttp PUT.
  - Удаление старых бэкапов по retention policy.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import aiohttp

import config as app_config
from backup.config import (
    BACKUP_RETENTION_DAYS,
    BACKUP_S3_BUCKET,
    BACKUP_S3_ENDPOINT,
    BACKUP_S3_KEY,
    BACKUP_S3_REGION,
    BACKUP_S3_SECRET,
)
from logging_config import get_logger

log = get_logger(__name__)


class BackupService:
    """Оркестрация бэкапов базы данных."""

    async def backup_postgres(self, db_url: str) -> bytes:
        """Выполнить pg_dump и вернуть дамп в байтах."""
        proc = await asyncio.create_subprocess_exec(
            "pg_dump", db_url, "--format=custom",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace")
            log.error("pg_dump_failed", returncode=proc.returncode, error=error_msg)
            raise RuntimeError(f"pg_dump failed: {error_msg}")

        log.info("pg_dump_success", size_bytes=len(stdout))
        return stdout

    def backup_sqlite(self, db_path: str) -> bytes:
        """Безопасно скопировать SQLite-файл через sqlite3.Connection.backup()."""
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"SQLite DB not found: {db_path}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            tmp_path = tmp.name

        try:
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(tmp_path)
            src.backup(dst)
            dst.close()
            src.close()

            with open(tmp_path, "rb") as f:
                data = f.read()
            log.info("sqlite_backup_success", path=db_path, size_bytes=len(data))
            return data
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def upload_to_s3(
        self,
        data: bytes,
        filename: str,
        bucket: str = "",
        key: str = "",
        secret: str = "",
        endpoint: str = "",
        region: str = "",
    ) -> bool:
        """Загрузить данные в S3-совместимое хранилище (PUT Object)."""
        bucket = bucket or BACKUP_S3_BUCKET
        key = key or BACKUP_S3_KEY
        secret = secret or BACKUP_S3_SECRET
        endpoint = endpoint or BACKUP_S3_ENDPOINT
        region = region or BACKUP_S3_REGION

        if not all([bucket, key, secret, endpoint]):
            log.error("s3_config_missing")
            return False

        # Path-style URL: endpoint/bucket/filename
        url = f"{endpoint}/{bucket}/{filename}"
        now = datetime.now(tz=timezone.utc)
        date_str = now.strftime("%Y%m%dT%H%M%SZ")
        date_short = now.strftime("%Y%m%d")

        # Compute content hash
        content_hash = hashlib.sha256(data).hexdigest()

        # Extract endpoint hostname for Host header (path-style: Host = endpoint host)
        parsed = urlparse(endpoint)
        host = parsed.netloc or parsed.path

        # Canonical request (path-style: Host is endpoint hostname)
        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{content_hash}\n"
            f"x-amz-date:{date_str}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"

        canonical_request = (
            f"PUT\n/{bucket}/{filename}\n\n"
            f"{canonical_headers}\n{signed_headers}\n{content_hash}"
        )

        # String to sign
        credential_scope = f"{date_short}/{region}/s3/aws4_request"
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{date_str}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        # Signing key derivation using _sign helper
        def _sign(k: bytes, msg: str) -> bytes:
            return hmac.new(k, msg.encode(), hashlib.sha256).digest()

        k_date = _sign(f"AWS4{secret}".encode(), date_short)
        k_region = _sign(k_date, region)
        k_service = _sign(k_region, "s3")
        k_signing = _sign(k_service, "aws4_request")

        signature = hmac.new(
            k_signing, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        auth_header = (
            f"AWS4-HMAC-SHA256 Credential={key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Host": host,
            "x-amz-date": date_str,
            "x-amz-content-sha256": content_hash,
            "Content-Type": "application/octet-stream",
            "Authorization": auth_header,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if 200 <= resp.status < 300:
                        log.info("s3_upload_success", filename=filename, size=len(data))
                        return True
                    body = await resp.text()
                    log.error("s3_upload_failed", status=resp.status, body=body[:200])
                    return False
        except (aiohttp.ClientError, Exception) as e:
            log.error("s3_upload_error", error=str(e))
            return False

    async def delete_old_backups(
        self,
        bucket: str = "",
        key: str = "",
        secret: str = "",
        endpoint: str = "",
        region: str = "",
        retention_days: int = 0,
    ) -> int:
        """Delete backups older than retention_days from S3.

        Returns the number of objects deleted.
        Note: This requires S3 ListObjects + DeleteObject support.
        Currently a stub that logs the intent - full implementation
        requires parsing S3 XML list responses.
        """
        retention_days = retention_days or BACKUP_RETENTION_DAYS
        bucket = bucket or BACKUP_S3_BUCKET
        endpoint = endpoint or BACKUP_S3_ENDPOINT

        if not all([bucket, endpoint, retention_days]):
            log.warning("backup_retention_skipped", reason="missing config")
            return 0

        # TODO: Implement full S3 ListObjectsV2 + DeleteObject for objects
        # whose LastModified is older than retention_days.
        # For now, log the intent.
        log.info(
            "backup_retention_check",
            bucket=bucket,
            retention_days=retention_days,
        )
        return 0

    async def run_backup(self) -> bool:
        """Основной процесс бэкапа: определить тип БД, сделать дамп, загрузить в S3."""
        db_url = app_config.DATABASE_URL
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        try:
            if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
                data = await self.backup_postgres(db_url)
                filename = f"backup_pg_{timestamp}.dump"
            else:
                # SQLite: извлекаем путь из URL
                db_path = db_url.replace("sqlite:///", "")
                data = self.backup_sqlite(db_path)
                filename = f"backup_sqlite_{timestamp}.db"

            success = await self.upload_to_s3(data, filename)
            if success:
                log.info("backup_completed", filename=filename)
                # Attempt retention cleanup
                await self.delete_old_backups()
            return success
        except Exception as e:
            log.error("backup_failed", error=str(e))
            return False
