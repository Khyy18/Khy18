"""Tests for core/backup.py - BackupManager."""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.backup import BackupManager


@pytest.fixture
def backup_manager(tmp_path: Path) -> BackupManager:
    """Create a BackupManager with a temporary backup directory."""
    return BackupManager(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/testdb",
        redis_url="redis://localhost:6379/0",
        backup_dir=str(tmp_path),
        retention_days=7,
    )


class TestRunPgDump:
    """Tests for BackupManager.run_pg_dump()."""

    async def test_run_pg_dump_success(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test successful pg_dump execution."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            # Create a fake dump file to simulate pg_dump output
            async def fake_communicate():
                # Simulate pg_dump creating the output file
                dump_files = list(tmp_path.glob("backup_testdb_*.dump"))
                if not dump_files:
                    # Find the file path from the command args
                    for call_args in mock_exec.call_args_list:
                        for arg in call_args[0]:
                            if isinstance(arg, str) and arg.startswith("--file="):
                                file_path = arg.replace("--file=", "")
                                # Create a file > 1KB
                                with open(file_path, "wb") as f:
                                    f.write(b"x" * 2048)
                return (b"", b"")

            mock_process.communicate = fake_communicate

            result = await backup_manager.run_pg_dump()

            assert result["success"] is True
            assert "testdb" in result["file_path"]
            assert result["size_bytes"] == 2048
            assert result["duration_seconds"] >= 0

            # Verify pg_dump was called with correct args
            call_args = mock_exec.call_args[0]
            assert "pg_dump" in call_args
            assert "--no-owner" in call_args
            assert "--format=custom" in call_args
            assert "--compress=9" in call_args
            assert "--host=localhost" in call_args
            assert "--port=5432" in call_args
            assert "--username=user" in call_args
            assert "testdb" in call_args

    async def test_run_pg_dump_failure(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test pg_dump failure handling."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"pg_dump: error: connection failed")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await backup_manager.run_pg_dump()

            assert result["success"] is False
            assert result["size_bytes"] == 0
            assert result["duration_seconds"] >= 0


class TestRotateBackups:
    """Tests for BackupManager.rotate_backups()."""

    async def test_rotate_backups_keeps_28(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test that rotation keeps at most 28 files and deletes oldest."""
        # Create 30 dump files with distinct mtimes
        for i in range(30):
            f = tmp_path / f"backup_testdb_{i:04d}.dump"
            f.write_bytes(b"data")
            # Set mtime to ensure ordering
            os.utime(f, (time.time() + i, time.time() + i))

        result = await backup_manager.rotate_backups()

        assert result["deleted_count"] == 2
        assert result["remaining_count"] == 28

        # Verify the 2 oldest were deleted (0000 and 0001)
        remaining_files = sorted(tmp_path.glob("*.dump"))
        remaining_names = [f.name for f in remaining_files]
        assert "backup_testdb_0000.dump" not in remaining_names
        assert "backup_testdb_0001.dump" not in remaining_names

    async def test_rotate_backups_no_delete_under_limit(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test that rotation does not delete files when under the limit."""
        # Create 10 dump files (well under 28 limit)
        for i in range(10):
            f = tmp_path / f"backup_testdb_{i:04d}.dump"
            f.write_bytes(b"data")

        result = await backup_manager.rotate_backups()

        assert result["deleted_count"] == 0
        assert result["remaining_count"] == 10


class TestVerifyBackup:
    """Tests for BackupManager.verify_backup()."""

    async def test_verify_backup_valid(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test verification passes for file > 1KB."""
        f = tmp_path / "valid_backup.dump"
        f.write_bytes(b"x" * 2048)  # 2KB file

        result = await backup_manager.verify_backup(str(f))
        assert result is True

    async def test_verify_backup_too_small(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test verification fails for file <= 1KB."""
        f = tmp_path / "small_backup.dump"
        f.write_bytes(b"x" * 512)  # 512 bytes

        result = await backup_manager.verify_backup(str(f))
        assert result is False

    async def test_verify_backup_missing(
        self, backup_manager: BackupManager, tmp_path: Path
    ) -> None:
        """Test verification fails for nonexistent path."""
        result = await backup_manager.verify_backup("/nonexistent/path/backup.dump")
        assert result is False


class TestTriggerRedisSnapshot:
    """Tests for BackupManager.trigger_redis_snapshot()."""

    async def test_trigger_redis_snapshot(
        self, backup_manager: BackupManager
    ) -> None:
        """Test Redis BGSAVE command is sent successfully."""
        mock_client = AsyncMock()
        mock_client.bgsave = AsyncMock()
        mock_client.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await backup_manager.trigger_redis_snapshot()

            assert result is True
            mock_client.bgsave.assert_called_once()
            mock_client.close.assert_called_once()


class TestAlertOnFailure:
    """Tests for BackupManager.alert_on_failure()."""

    async def test_alert_on_failure(
        self, backup_manager: BackupManager
    ) -> None:
        """Test Telegram alert is sent on backup failure."""
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await backup_manager.alert_on_failure(
                error_msg="pg_dump failed",
                telegram_bot_token="test_token",
                telegram_chat_id="12345",
            )

            mock_session_instance.post.assert_called_once()
            call_args = mock_session_instance.post.call_args
            assert "test_token" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "12345"
            assert "pg_dump failed" in call_args[1]["json"]["text"]
