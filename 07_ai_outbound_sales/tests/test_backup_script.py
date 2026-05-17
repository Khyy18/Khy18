"""Tests for the standalone backup script."""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import the backup script module
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import backup as backup_module


class TestParseDatabaseUrl:
    """Tests for parse_database_url function."""

    def test_standard_postgresql_url(self):
        url = "postgresql://user:pass@localhost:5432/mydb"
        result = backup_module.parse_database_url(url)
        assert result["host"] == "localhost"
        assert result["port"] == "5432"
        assert result["user"] == "user"
        assert result["password"] == "pass"
        assert result["dbname"] == "mydb"

    def test_asyncpg_url_format(self):
        url = "postgresql+asyncpg://admin:secret@db.example.com:5433/salesdb"
        result = backup_module.parse_database_url(url)
        assert result["host"] == "db.example.com"
        assert result["port"] == "5433"
        assert result["user"] == "admin"
        assert result["password"] == "secret"
        assert result["dbname"] == "salesdb"

    def test_defaults_for_minimal_url(self):
        url = "postgresql://localhost/testdb"
        result = backup_module.parse_database_url(url)
        assert result["host"] == "localhost"
        assert result["port"] == "5432"
        assert result["user"] == "postgres"
        assert result["password"] == ""
        assert result["dbname"] == "testdb"


class TestRunPgDump:
    """Tests for run_pg_dump function."""

    def test_pg_dump_success(self):
        db_params = {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "secret",
            "dbname": "testdb",
        }
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as f:
            output_path = f.name

        try:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""

            with patch("backup.subprocess.run", return_value=mock_result) as mock_run:
                result = backup_module.run_pg_dump(db_params, output_path)
                assert result is True
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                cmd = call_args[0][0]
                assert "pg_dump" in cmd[0]
                assert f"--host={db_params['host']}" in cmd
                assert f"--port={db_params['port']}" in cmd
                assert f"--username={db_params['user']}" in cmd
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_pg_dump_failure(self):
        db_params = {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "secret",
            "dbname": "testdb",
        }
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "connection refused"

        with patch("backup.subprocess.run", return_value=mock_result):
            result = backup_module.run_pg_dump(db_params, "/tmp/test.dump")
            assert result is False

    def test_pg_dump_not_found(self):
        db_params = {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "",
            "dbname": "testdb",
        }
        with patch("backup.subprocess.run", side_effect=FileNotFoundError):
            result = backup_module.run_pg_dump(db_params, "/tmp/test.dump")
            assert result is False


class TestApplyRetention:
    """Tests for apply_retention function."""

    def test_retention_removes_old_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 15 daily backup files
            for i in range(15):
                day = f"2024010{i+1}" if i < 9 else f"202401{i+1}"
                path = Path(tmpdir) / f"backup_testdb_{day}_120000.dump"
                path.write_bytes(b"fake backup data")
                # Set modification time to spread across days
                mtime = datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
                os.utime(path, (mtime, mtime))

            backup_module.apply_retention(tmpdir)

            remaining = list(Path(tmpdir).glob("backup_*.dump"))
            # Should keep at most 7 daily + 4 weekly (with overlap, likely <= 11)
            assert len(remaining) <= 11
            assert len(remaining) >= 4  # At least weekly retention

    def test_retention_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise
            backup_module.apply_retention(tmpdir)

    def test_retention_nonexistent_dir(self):
        # Should not raise
        backup_module.apply_retention("/nonexistent/path/that/does/not/exist")


class TestUploadToS3:
    """Tests for upload_to_s3 function."""

    def test_s3_upload_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch.dict(os.environ, {"AWS_S3_BUCKET": "my-bucket"}), \
             patch.object(backup_module, "AWS_S3_BUCKET", "my-bucket"), \
             patch("backup.subprocess.run", return_value=mock_result):
            result = backup_module.upload_to_s3("/tmp/backup_test.dump")
            assert result is True

    def test_s3_upload_no_bucket(self):
        with patch.object(backup_module, "AWS_S3_BUCKET", ""):
            result = backup_module.upload_to_s3("/tmp/backup_test.dump")
            assert result is False


class TestSendTelegramNotification:
    """Tests for send_telegram_notification function."""

    def test_not_configured(self):
        with patch.object(backup_module, "TELEGRAM_BOT_TOKEN", ""), \
             patch.object(backup_module, "TELEGRAM_CHAT_ID", ""):
            result = backup_module.send_telegram_notification("test message")
            assert result is False

    def test_send_success(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch.object(backup_module, "TELEGRAM_BOT_TOKEN", "bot123"), \
             patch.object(backup_module, "TELEGRAM_CHAT_ID", "456"), \
             patch("urllib.request.urlopen", return_value=mock_response):
            result = backup_module.send_telegram_notification("Backup OK")
            assert result is True


class TestMain:
    """Tests for the main backup workflow."""

    def test_main_no_database_url(self):
        with patch.object(backup_module, "DATABASE_URL", ""), \
             patch.object(backup_module, "send_telegram_notification") as mock_notify:
            result = backup_module.main()
            assert result == 1
            mock_notify.assert_called_once()

    def test_main_success_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(backup_module, "DATABASE_URL", "postgresql://user:pass@localhost/testdb"), \
                 patch.object(backup_module, "BACKUP_MODE", "local"), \
                 patch.object(backup_module, "BACKUP_DIR", tmpdir), \
                 patch.object(backup_module, "run_pg_dump") as mock_dump, \
                 patch.object(backup_module, "apply_retention") as mock_retain, \
                 patch.object(backup_module, "send_telegram_notification") as mock_notify:
                # Simulate pg_dump creating a file
                mock_dump.return_value = True

                # Create a fake output file so os.path.getsize works
                def create_fake_dump(db_params, output_path):
                    Path(output_path).write_bytes(b"x" * 1024)
                    return True

                mock_dump.side_effect = create_fake_dump

                result = backup_module.main()
                assert result == 0
                mock_retain.assert_called_once_with(tmpdir)
                mock_notify.assert_called_once()

    def test_main_pg_dump_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(backup_module, "DATABASE_URL", "postgresql://user:pass@localhost/testdb"), \
                 patch.object(backup_module, "BACKUP_MODE", "local"), \
                 patch.object(backup_module, "BACKUP_DIR", tmpdir), \
                 patch.object(backup_module, "run_pg_dump", return_value=False), \
                 patch.object(backup_module, "send_telegram_notification") as mock_notify:
                result = backup_module.main()
                assert result == 1
                mock_notify.assert_called_once()
