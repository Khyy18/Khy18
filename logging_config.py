"""Настройка логирования для арбитражного модуля."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging() -> None:
    """Настроить логирование: консоль + ротируемый файл."""
    level_name = os.getenv("ARB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt)

    root_logger = logging.getLogger("arbitrage")
    root_logger.setLevel(level)

    # Избегаем дублирования хендлеров при повторном вызове
    if root_logger.handlers:
        return

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

    # File handler with rotation
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbitrage.log")
    fh = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)
