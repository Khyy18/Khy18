"""Модуль абстракции базы данных.

Предоставляет единый интерфейс StorageProtocol (sync) и AsyncStorageProtocol (async),
а также фабрику get_storage() для переключения между SQLite (dev) и PostgreSQL (prod).
"""

from db.factory import get_storage
from db.protocol import AsyncStorageProtocol, StorageProtocol

__all__ = ["AsyncStorageProtocol", "StorageProtocol", "get_storage"]
