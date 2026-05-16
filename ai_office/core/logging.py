"""Structured JSON logging с correlation ID и context propagation."""

import contextvars
import json
import logging
import sys
import traceback
from datetime import datetime, timezone


# Context variables for correlation and agent tracking
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
agent_context_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agent_name", default=""
)


class StructuredJsonFormatter(logging.Formatter):
    """Форматтер для JSON-структурированного логирования."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as single-line JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(""),
            "agent_name": agent_context_var.get(""),
        }

        # Add extra fields if present
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry.update(record.extra_data)

        # Add exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc_info"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Простой текстовый форматтер для разработки."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as readable text."""
        correlation_id = correlation_id_var.get("")
        agent_name = agent_context_var.get("")
        prefix = ""
        if correlation_id:
            prefix += f"[{correlation_id[:8]}] "
        if agent_name:
            prefix += f"[{agent_name}] "
        return f"{record.levelname} {prefix}{record.module}: {record.getMessage()}"


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that includes context vars in extra."""

    def process(self, msg, kwargs):
        """Add context information to log records."""
        extra = kwargs.get("extra", {})
        extra["correlation_id"] = correlation_id_var.get("")
        extra["agent_name"] = agent_context_var.get("")
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Настроить корневой логгер с JSON или text форматтером.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR).
        log_format: Формат вывода - 'json' или 'text'.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if log_format == "json":
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root_logger.addHandler(handler)


def get_logger(name: str) -> ContextLogger:
    """Получить логгер с поддержкой контекста.

    Args:
        name: Имя логгера (обычно __name__).

    Returns:
        ContextLogger с автоматической подстановкой correlation_id и agent_name.
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})
