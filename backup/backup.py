"""Сервис бэкапов: PostgreSQL (pg_dump), SQLite (copy), S3 upload.

Поддерживает:
  - PostgreSQL: через asyncio subprocess (pg_dump).
  - SQLite: копирование файла.
  - Загрузка в S3-совместимое хранилище через aiohttp PUT.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Optional

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
        """Скопировать SQLite-файл и вернуть содержимое."""
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"SQLite DB not found: {db_path}")

        # Используем временный файл для безопасного копирования
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            shutil.copy2(db_path, tmp_path)
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

        url = f"{endpoint}/{bucket}/{filename}"
        now = datetime.now(tz=timezone.utc)
        date_str = now.strftime("%Y%m%dT%H%M%SZ")
        date_short = now.strftime("%Y%m%d")

        # Simplified AWS Signature V4 for PUT
        content_hash = hashlib.sha256(data).hexdigest()
        headers = {
            "x-amz-date": date_str,
            "x-amz-content-sha256": content_hash,
            "Content-Type": "application/octet-stream",
        }

        # Canonical request
        canonical_headers = (
            f"host:{bucket}.{endpoint.replace('https://', '').replace('http://', '')}\n"
            f"x-amz-content-sha256:{content_hash}\n"
            f"x-amz-date:{date_str}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"

        canonical_request = (
            f"PUT\n/{filename}\n\n"
            f"{canonical_headers}\n{signed_headers}\n{content_hash}"
        )

        # String to sign
        credential_scope = f"{date_short}/{region}/s3/aws4_request"
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{date_str}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        # Signing key
        def _sign(k: bytes, msg: str) -> bytes:
            return hmac.new(k, msg.encode(), hashlib.sha256).digest()

        k_date = hmac.new(
            f"AWS4{secret}".encode(), date_short.encode(), hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

        signature = hmac.new(
            k_signing, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        auth_header = (
            f"AWS4-HMAC-SHA256 Credential={key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers["Authorization"] = auth_header

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, data=data, headers=headers, timeout=60) as resp:
                    if 200 <= resp.status < 300:
                        log.info("s3_upload_success", filename=filename, size=len(data))
                        return True
                    body = await resp.text()
                    log.error("s3_upload_failed", status=resp.status, body=body[:200])
                    return False
        except (aiohttp.ClientError, Exception) as e:
            log.error("s3_upload_error", error=str(e))
            return False

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
            return success
        except Exception as e:
            log.error("backup_failed", error=str(e))
            return False
