"""Tests for backup handler - /backup command and auto-backup job."""

import datetime
import os
import sqlite3
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kindergarten_accountant_bot.handlers.backup_handler import (
    backup_command,
    setup_backup_jobs,
    _auto_backup_job,
    _send_backup,
)


def _make_update_and_context(chat_id=12345):
    """Create mock Update and Context for backup command."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_message = AsyncMock()
    return update, context


class TestBackupCommand:
    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BOT_ADMIN_IDS", "12345,67890")
    @patch("kindergarten_accountant_bot.handlers.backup_handler.get_db_path")
    async def test_backup_sends_document(self, mock_db_path, tmp_path):
        """Backup command copies DB and sends as document."""
        # Create a temporary SQLite DB file
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.close()
        mock_db_path.return_value = str(db_file)

        update, context = _make_update_and_context(chat_id=12345)

        await backup_command(update, context)

        context.bot.send_document.assert_called_once()
        call_kwargs = context.bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 12345
        today = datetime.date.today().strftime("%Y-%m-%d")
        assert call_kwargs["filename"] == f"backup_{today}.db"

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BOT_ADMIN_IDS", "67890")
    async def test_backup_denied_for_non_admin(self):
        """Backup command denies access for non-admin users."""
        update, context = _make_update_and_context(chat_id=12345)

        await backup_command(update, context)

        update.message.reply_text.assert_called_once()
        assert "нет доступа" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BOT_ADMIN_IDS", "")
    @patch("kindergarten_accountant_bot.handlers.backup_handler.get_db_path")
    async def test_backup_allowed_when_no_admins_configured(self, mock_db_path, tmp_path):
        """Backup command works when BOT_ADMIN_IDS is empty (no restriction)."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.close()
        mock_db_path.return_value = str(db_file)

        update, context = _make_update_and_context(chat_id=99999)

        await backup_command(update, context)

        context.bot.send_document.assert_called_once()

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.get_db_path")
    async def test_backup_handles_missing_db(self, mock_db_path):
        """Backup command handles missing DB file gracefully."""
        mock_db_path.return_value = "/nonexistent/path/bot.db"

        bot = MagicMock()
        bot.send_document = AsyncMock()
        bot.send_message = AsyncMock()

        await _send_backup(bot, 12345)

        bot.send_message.assert_called_once()
        assert "не найден" in bot.send_message.call_args[1]["text"]


class TestAutoBackupJob:
    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BACKUP_CHAT_IDS", "111,222")
    @patch("kindergarten_accountant_bot.handlers.backup_handler.get_db_path")
    async def test_auto_backup_sends_to_all_ids(self, mock_db_path, tmp_path):
        """Auto-backup sends to all configured chat IDs."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.close()
        mock_db_path.return_value = str(db_file)

        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_document = AsyncMock()
        context.bot.send_message = AsyncMock()

        await _auto_backup_job(context)

        assert context.bot.send_document.call_count == 2

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BACKUP_CHAT_IDS", "")
    @patch("kindergarten_accountant_bot.handlers.backup_handler.BOT_ADMIN_IDS", "333")
    @patch("kindergarten_accountant_bot.handlers.backup_handler.get_db_path")
    async def test_auto_backup_fallback_to_admin_ids(self, mock_db_path, tmp_path):
        """Auto-backup uses BOT_ADMIN_IDS when BACKUP_CHAT_IDS is empty."""
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.close()
        mock_db_path.return_value = str(db_file)

        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_document = AsyncMock()
        context.bot.send_message = AsyncMock()

        await _auto_backup_job(context)

        assert context.bot.send_document.call_count == 1
        call_kwargs = context.bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 333


class TestSetupBackupJobs:
    def test_setup_schedules_daily_job(self):
        """setup_backup_jobs schedules a daily job at 23:00 Moscow."""
        app = MagicMock()
        app.job_queue = MagicMock()
        app.job_queue.run_daily = MagicMock()

        setup_backup_jobs(app)

        app.job_queue.run_daily.assert_called_once()
        call_kwargs = app.job_queue.run_daily.call_args[1]
        assert call_kwargs["name"] == "auto_backup_daily"
        job_time = call_kwargs["time"]
        assert job_time.hour == 23
        assert job_time.minute == 0
        # Verify Moscow timezone (UTC+3)
        assert job_time.tzinfo == datetime.timezone(datetime.timedelta(hours=3))
