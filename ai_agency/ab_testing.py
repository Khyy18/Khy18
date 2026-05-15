"""A/B тестирование промптов с алгоритмом UCB1."""

import math
import logging
from typing import Optional, Tuple, List

import aiosqlite
import config

logger = logging.getLogger(__name__)


async def init_ab_tables() -> None:
    """Создать таблицу ab_variants если не существует."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ab_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                variant_name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                total_uses INTEGER NOT NULL DEFAULT 0,
                total_score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def select_variant(service_type: str) -> Optional[Tuple[int, str]]:
    """
    Выбрать вариант промпта для A/B теста по алгоритму UCB1.

    UCB1: если у варианта < 5 использований - выбрать его (exploration).
    Иначе: argmax(avg_score + sqrt(2 * ln(total_uses_all) / uses_i)).

    Возвращает (variant_id, system_prompt) или None если вариантов нет.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ab_variants WHERE service_type = ?",
            (service_type,),
        )
        variants = await cursor.fetchall()

        if not variants:
            return None

        # Exploration: если есть вариант с < 5 использований, выбираем его
        for v in variants:
            if v["total_uses"] < 5:
                return (v["id"], v["system_prompt"])

        # UCB1: вычисляем суммарное количество использований
        total_uses_all = sum(v["total_uses"] for v in variants)
        if total_uses_all == 0:
            # Все варианты с 0 использований - берем первый
            v = variants[0]
            return (v["id"], v["system_prompt"])

        best_variant = None
        best_ucb = -1.0

        for v in variants:
            uses = v["total_uses"]
            if uses == 0:
                # Неиспользованный вариант - приоритет
                return (v["id"], v["system_prompt"])
            avg_score = v["total_score"] / uses
            ucb_value = avg_score + math.sqrt(2 * math.log(total_uses_all) / uses)
            if ucb_value > best_ucb:
                best_ucb = ucb_value
                best_variant = v

        if best_variant:
            return (best_variant["id"], best_variant["system_prompt"])
        return None


async def record_result(variant_id: int, rating: int) -> None:
    """
    Записать результат A/B теста: атомарно инкрементировать
    total_uses и добавить rating к total_score.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """UPDATE ab_variants
               SET total_uses = total_uses + 1, total_score = total_score + ?
               WHERE id = ?""",
            (float(rating), variant_id),
        )
        await db.commit()


async def get_best_variant(service_type: str) -> Optional[dict]:
    """
    Получить лучший вариант для услуги (с наибольшим средним score
    при >= 10 использований).

    Возвращает dict с полями варианта или None.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT *, (total_score / total_uses) as avg_score
               FROM ab_variants
               WHERE service_type = ? AND total_uses >= 10
               ORDER BY avg_score DESC
               LIMIT 1""",
            (service_type,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_variant(service_type: str, variant_name: str, system_prompt: str) -> int:
    """Добавить новый вариант промпта для A/B тестирования."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO ab_variants (service_type, variant_name, system_prompt)
               VALUES (?, ?, ?)""",
            (service_type, variant_name, system_prompt),
        )
        await db.commit()
        return cursor.lastrowid
