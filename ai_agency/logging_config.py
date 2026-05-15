"""Настройка структурированного логирования с ротацией и опциональной интеграцией Sentry."""

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Optional

import config


class JSONFormatter(logging.Formatter):
    """Форматтер для JSON-логов с поддержкой доп. полей заказа."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Дополнительные поля заказа
        for field in ("order_id", "client_id", "duration", "status"):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Человекочитаемый форматтер для консоли."""

    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    def __init__(self):
        super().__init__(fmt=self.FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Настроить корневой логгер с консольным и файловым хендлерами.

    Консоль: человекочитаемый формат.
    Файл: JSON с ротацией (10MB, 5 файлов).
    Опционально: Sentry интеграция если SENTRY_DSN задан.
    """
    log_level = getattr(logging, (level or config.LOG_LEVEL).upper(), logging.INFO)
    log_path = log_file or config.LOG_FILE

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Очищаем существующие хендлеры
    root_logger.handlers.clear()

    # Консольный хендлер
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    # Файловый хендлер с ротацией (10MB, 5 файлов)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # Sentry интеграция (опционально)
    if config.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=config.SENTRY_DSN)
            root_logger.info("Sentry интеграция активирована")
        except ImportError:
            root_logger.warning("sentry_sdk не установлен, Sentry интеграция пропущена")

    root_logger.info("Логирование настроено: level=%s, file=%s", log_level, log_path)
    return root_logger
