"""Фабрика для создания экземпляра хранилища на основе URL.

Определяет тип бэкенда по схеме URL:
  - sqlite:///... -> SQLiteBackend (синхронный, реализует StorageProtocol)
  - postgresql://... или postgres://... -> PostgresBackend (асинхронный, реализует AsyncStorageProtocol)

ВАЖНО: sync/async разделение протоколов.
  SQLiteBackend - синхронный, вызывается напрямую: storage.record_trade(...)
  PostgresBackend - асинхронный, требует await: await storage.record_trade(...)
  Также PostgresBackend требует вызова await storage.connect() перед использованием
  и await storage.close() при завершении.
  Вызывающий код должен проверять тип бэкенда или использовать
  AsyncStorageProtocol из db.protocol для type-checking.
"""

from __future__ import annotations

from typing import Union

from db.sqlite_backend import SQLiteBackend


def get_storage(url: str) -> Union[SQLiteBackend, "PostgresBackend"]:  # noqa: F821
    """Вернуть экземпляр хранилища на основе URL.

    Для SQLite URL формата sqlite:///path/to/db.db
    Для PostgreSQL URL формата postgresql://user:pass@host/db

    Возвращает SQLiteBackend для SQLite URL.
    Для PostgreSQL возвращает PostgresBackend (требует asyncpg, async callers).
    """
    scheme = url.split("://")[0].lower() if "://" in url else ""

    if scheme in ("postgresql", "postgres"):
        from db.postgres_backend import PostgresBackend
        return PostgresBackend(dsn=url)

    # По умолчанию SQLite
    # Поддерживаем форматы: sqlite:///path, sqlite:///./path, просто path
    if scheme == "sqlite":
        # sqlite:///trades.db -> trades.db
        # sqlite:////absolute/path.db -> /absolute/path.db
        path = url.split(":///", 1)[1] if ":///" in url else url
    else:
        path = url

    return SQLiteBackend(db_path=path)
