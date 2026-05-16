"""Backup handler - manual /backup command and auto-backup job."""

import datetime
import logging
import sqlite3
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.config import (
    BACKUP_CHAT_IDS,
    BOT_ADMIN_IDS,
    get_db_path,
)

logger = logging.getLogger(__name__)

MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /backup command - send current DB as a document."""
    chat_id = update.effective_chat.id

    # Check if user is admin
    admin_ids = [
        int(x.strip()) for x in BOT_ADMIN_IDS.split(",") if x.strip()
    ]
    if admin_ids and chat_id not in admin_ids:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    await _send_backup(context.bot, chat_id)


async def _send_backup(bot, chat_id: int) -> None:
    """Copy the DB file and send it as a document to the specified chat."""
    import os

    db_path = get_db_path()
    today = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"backup_{today}.db"

    if not os.path.exists(db_path):
        await bot.send_message(
            chat_id=chat_id,
            text="Файл базы данных не найден.",
        )
        return

    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        # Use sqlite3 online backup API for a consistent snapshot
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()

        with open(tmp_path, "rb") as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=filename,
                caption=f"Резервная копия базы данных ({today})",
            )
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка создания резервной копии: {e}",
        )


async def _auto_backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback for daily auto-backup."""
    # Collect chat IDs from BACKUP_CHAT_IDS, fallback to BOT_ADMIN_IDS
    raw_ids = BACKUP_CHAT_IDS or BOT_ADMIN_IDS
    chat_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]

    for chat_id in chat_ids:
        try:
            await _send_backup(context.bot, chat_id)
        except Exception as e:
            logger.error(f"Auto-backup to {chat_id} failed: {e}")


def setup_backup_jobs(app) -> None:
    """Schedule daily auto-backup at 23:00 Moscow time."""
    backup_time = datetime.time(hour=23, minute=0, tzinfo=MOSCOW_TZ)
    app.job_queue.run_daily(
        _auto_backup_job,
        time=backup_time,
        name="auto_backup_daily",
    )
