"""Автоматическое резервное копирование SQLite базы данных."""

import logging
import os
import shutil
from datetime import datetime
from typing import List

import config

logger = logging.getLogger(__name__)


async def backup_database() -> str:
    """
    Создать резервную копию базы данных.

    Копирует DATABASE_PATH в BACKUP_DIR с таймстампом.
    Возвращает путь к созданной копии.
    """
    backup_dir = config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"agency_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    db_path = config.DATABASE_PATH
    if not os.path.exists(db_path):
        logger.warning("БД не найдена: %s, бэкап пропущен", db_path)
        return ""

    shutil.copy2(db_path, backup_path)
    file_size = os.path.getsize(backup_path)
    logger.info(
        "Бэкап создан: %s (%.2f MB)",
        backup_path,
        file_size / (1024 * 1024),
    )
    return backup_path


async def cleanup_old_backups(keep: int = None) -> int:
    """
    Удалить старые бэкапы, оставив только последние N.

    Возвращает количество удалённых файлов.
    """
    keep_count = keep if keep is not None else config.BACKUP_KEEP_COUNT
    backup_dir = config.BACKUP_DIR

    if not os.path.exists(backup_dir):
        return 0

    # Собираем все файлы бэкапов
    backups: List[str] = sorted(
        [
            f
            for f in os.listdir(backup_dir)
            if f.startswith("agency_backup_") and f.endswith(".db")
        ]
    )

    if len(backups) <= keep_count:
        return 0

    # Удаляем самые старые
    to_delete = backups[: len(backups) - keep_count]
    deleted = 0
    for filename in to_delete:
        filepath = os.path.join(backup_dir, filename)
        try:
            os.remove(filepath)
            deleted += 1
            logger.debug("Удалён старый бэкап: %s", filename)
        except OSError as e:
            logger.warning("Не удалось удалить бэкап %s: %s", filename, e)

    if deleted:
        logger.info("Очистка бэкапов: удалено %d, оставлено %d", deleted, keep_count)
    return deleted
