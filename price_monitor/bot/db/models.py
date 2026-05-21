"""Инициализация базы данных - делегирует в SQLAlchemy session."""
from __future__ import annotations

from bot.db.session import init_db  # noqa: F401

__all__ = ["init_db"]
