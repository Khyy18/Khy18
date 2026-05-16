"""Тесты для backup/ модуля: SQLite backup, S3 upload (mocked)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backup.backup import BackupService


def test_backup_sqlite_copies_file(tmp_path):
    """backup_sqlite корректно копирует файл."""
    db_path = str(tmp_path / "test.db")
    content = b"SQLite format 3\x00" + b"\x00" * 100
    with open(db_path, "wb") as f:
        f.write(content)

    service = BackupService()
    result = service.backup_sqlite(db_path)

    assert result == content
    assert len(result) == len(content)


def test_backup_sqlite_file_not_found():
    """backup_sqlite выбрасывает ошибку если файл не найден."""
    service = BackupService()

    with pytest.raises(FileNotFoundError):
        service.backup_sqlite("/nonexistent/path/db.sqlite")


@pytest.mark.asyncio
async def test_upload_to_s3_success():
    """upload_to_s3 возвращает True при успешном ответе."""
    service = BackupService()

    mock_resp = MagicMock()
    mock_resp.status = 200

    mock_session = MagicMock()

    @asynccontextmanager
    async def _put(*args, **kwargs):
        yield mock_resp

    mock_session.put = _put
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("backup.backup.aiohttp.ClientSession", return_value=mock_session):
        result = await service.upload_to_s3(
            data=b"test data",
            filename="backup_test.db",
            bucket="test-bucket",
            key="AKIATEST",
            secret="secretkey123",
            endpoint="https://s3.example.com",
            region="us-east-1",
        )

    assert result is True


@pytest.mark.asyncio
async def test_upload_to_s3_failure():
    """upload_to_s3 возвращает False при ошибке HTTP."""
    service = BackupService()

    mock_resp = MagicMock()
    mock_resp.status = 403
    mock_resp.text = AsyncMock(return_value="Forbidden")

    mock_session = MagicMock()

    @asynccontextmanager
    async def _put(*args, **kwargs):
        yield mock_resp

    mock_session.put = _put
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("backup.backup.aiohttp.ClientSession", return_value=mock_session):
        result = await service.upload_to_s3(
            data=b"test data",
            filename="backup_test.db",
            bucket="test-bucket",
            key="AKIATEST",
            secret="secretkey123",
            endpoint="https://s3.example.com",
            region="us-east-1",
        )

    assert result is False


@pytest.mark.asyncio
async def test_upload_to_s3_missing_config():
    """upload_to_s3 возвращает False при отсутствии конфигурации."""
    service = BackupService()

    result = await service.upload_to_s3(
        data=b"test data",
        filename="backup.db",
        bucket="",
        key="",
        secret="",
        endpoint="",
    )

    assert result is False


@pytest.mark.asyncio
async def test_run_backup_sqlite(tmp_path):
    """run_backup для SQLite: делает бэкап и вызывает upload."""
    db_path = str(tmp_path / "test.db")
    with open(db_path, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 50)

    service = BackupService()

    with patch.object(service, "upload_to_s3", new_callable=AsyncMock, return_value=True) as mock_upload:
        with patch("backup.backup.app_config") as mock_config:
            mock_config.DATABASE_URL = f"sqlite:///{db_path}"
            result = await service.run_backup()

    assert result is True
    mock_upload.assert_called_once()
    # Проверяем что filename содержит sqlite
    call_args = mock_upload.call_args
    filename_arg = call_args[0][1]  # positional arg: data, filename
    assert "sqlite" in filename_arg
