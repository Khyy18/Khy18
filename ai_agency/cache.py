"""Семантический кеш AI-агентства: SHA256 хеширование, TTL, статистика."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Счётчики для статистики (in-memory)
_cache_hits: int = 0
_cache_misses: int = 0


def cache_key(service_type: str, input_text: str) -> str:
    """
    Сгенерировать ключ кеша: SHA256 хеш нормализованного ввода.

    Нормализация: lowercase + strip.
    """
    normalized = f"{service_type}:{input_text.lower().strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_cached_result(service_type: str, input_text: str) -> Optional[str]:
    """
    Получить результат из кеша.

    Сначала проверяет точное совпадение по хешу.
    Если embeddings недоступны, используется только exact match.
    """
    global _cache_hits, _cache_misses

    input_hash = cache_key(service_type, input_text)
    now = datetime.utcnow().isoformat()

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Точное совпадение по хешу
        cursor = await db.execute(
            """SELECT id, result_text FROM semantic_cache
               WHERE service_type = ? AND input_hash = ? AND expires_at > ?
               LIMIT 1""",
            (service_type, input_hash, now),
        )
        row = await cursor.fetchone()

        if row:
            cache_id = row[0]
            result_text = row[1]
            # Инкрементируем hit_count
            await db.execute(
                "UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = ?",
                (cache_id,),
            )
            await db.commit()
            _cache_hits += 1
            logger.debug("Cache HIT для %s (hash=%s...)", service_type, input_hash[:8])
            return result_text

    _cache_misses += 1
    logger.debug("Cache MISS для %s (hash=%s...)", service_type, input_hash[:8])
    return None


async def store_result(service_type: str, input_text: str, result_text: str) -> None:
    """
    Сохранить результат в кеш с TTL.

    TTL задаётся через config.CACHE_TTL_DAYS (по умолчанию 7 дней).
    """
    input_hash = cache_key(service_type, input_text)
    expires_at = (datetime.utcnow() + timedelta(days=config.CACHE_TTL_DAYS)).isoformat()

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Upsert: удаляем старую запись если есть
        await db.execute(
            "DELETE FROM semantic_cache WHERE service_type = ? AND input_hash = ?",
            (service_type, input_hash),
        )
        await db.execute(
            """INSERT INTO semantic_cache
               (service_type, input_hash, result_text, expires_at)
               VALUES (?, ?, ?, ?)""",
            (service_type, input_hash, result_text, expires_at),
        )
        await db.commit()

    logger.debug("Cache STORE для %s (hash=%s...)", service_type, input_hash[:8])


async def get_cache_stats() -> Dict[str, int]:
    """
    Получить статистику кеша: hit rate, total hits, misses.
    """
    total = _cache_hits + _cache_misses
    hit_rate = (_cache_hits / total * 100) if total > 0 else 0.0

    # Подсчитываем записи в БД
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM semantic_cache")
        row = await cursor.fetchone()
        total_entries = row[0] if row else 0

        cursor2 = await db.execute("SELECT COALESCE(SUM(hit_count), 0) FROM semantic_cache")
        row2 = await cursor2.fetchone()
        total_db_hits = row2[0] if row2 else 0

    return {
        "session_hits": _cache_hits,
        "session_misses": _cache_misses,
        "session_hit_rate": round(hit_rate, 1),
        "total_entries": total_entries,
        "total_db_hits": total_db_hits,
    }


async def cleanup_expired() -> int:
    """Удалить просроченные записи из кеша. Возвращает количество удалённых."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM semantic_cache WHERE expires_at <= ?",
            (now,),
        )
        count = cursor.rowcount
        await db.commit()
    return count
