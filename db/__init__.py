"""Модуль абстракции базы данных.

Предоставляет единый интерфейс StorageProtocol и фабрику get_storage()
для переключения между SQLite (dev) и PostgreSQL (prod) бэкендами.
"""

from db.factory import get_storage
from db.protocol import StorageProtocol

__all__ = ["StorageProtocol", "get_storage"]
