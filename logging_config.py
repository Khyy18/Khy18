"""Конфигурация структурированного логирования (structlog).

Режимы:
  - "json" (prod): машиночитаемый JSON, одна строка на событие.
  - "console" (dev): цветной вывод с отступами для удобства отладки.

Режим определяется переменной окружения LOG_FORMAT (по умолчанию "console").
"""

from __future__ import annotations

import logging
import sys

import structlog


def _configure_structlog(log_format: str = "console") -> None:
    """Настроить structlog: процессоры, рендерер, привязку к stdlib logging."""
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Настройка stdlib logging для перехвата сторонних библиотек
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def setup_logging(log_format: str | None = None) -> None:
    """Инициализировать логирование. Вызывать один раз при старте приложения."""
    import os
    fmt = log_format or os.getenv("LOG_FORMAT", "console")
    _configure_structlog(fmt)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Получить именованный структурированный логгер.

    Использование:
        from logging_config import get_logger
        log = get_logger(__name__)
        log.info("событие", key="value")
    """
    return structlog.get_logger(name)
