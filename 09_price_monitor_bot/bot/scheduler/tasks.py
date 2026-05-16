"""Задачи планировщика APScheduler для бота мониторинга цен."""

import logging
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from bot.config import settings
from bot.db.queries import (
    add_price_record,
    get_price_history,
    get_product_by_external_id,
    add_post,
)
from bot.parsers.wildberries import WildberriesParser
from bot.parsers.ozon import OzonParser
from bot.ai.antifraud import AntifraudDetector
from bot.ai.ranker import ProductRanker
from bot.ai.post_generator import PostGenerator
from bot.ai.reviews_summary import ReviewsSummarizer

logger = logging.getLogger(__name__)

# Минимальная скидка для публикации (%)
_MIN_DISCOUNT_FOR_PUBLISH = 15


async def parse_prices_job() -> None:
    """Парсинг цен для всех отслеживаемых товаров.

    - Получает цены с WB и Ozon
    - Сохраняет в БД
    - Проверяет антифрод
    - Для товаров с реальной скидкой >15% запускает пайплайн публикации
    """
    logger.info("Запуск задачи парсинга цен...")

    wb_parser = WildberriesParser()
    ozon_parser = OzonParser()
    antifraud = AntifraudDetector()
    ranker = ProductRanker()
    post_gen = PostGenerator()
    reviews_summarizer = ReviewsSummarizer()

    try:
        # Получаем все отслеживаемые товары из БД
        products = await _get_tracked_products()

        genuine_discounts: list[dict[str, Any]] = []

        for product in products:
            marketplace = product.get("marketplace", "")
            external_id = product.get("external_id", "")

            # Парсим текущую цену
            current_data = None
            if marketplace == "wildberries":
                current_data = await wb_parser.fetch_product(external_id)
            elif marketplace == "ozon":
                current_data = await ozon_parser.fetch_product(external_id)

            if not current_data:
                continue

            price = current_data.get("price", 0)
            old_price = current_data.get("old_price", 0)
            discount = current_data.get("discount", 0)

            # Получаем историю цен
            history_records = await get_price_history(product["id"])
            price_history = [r["price"] for r in history_records]

            # Проверяем антифрод
            fraud_result = await antifraud.is_fake_discount(
                external_id, price, old_price, price_history
            )

            # Сохраняем запись о цене
            await add_price_record(
                product_id=product["id"],
                price=price,
                old_price=old_price,
                discount_percent=discount,
                is_fraud=fraud_result.is_fraud,
            )

            # Если скидка реальная и >15%, добавляем в кандидаты для публикации
            if not fraud_result.is_fraud and discount >= _MIN_DISCOUNT_FOR_PUBLISH:
                current_data["product_db_id"] = product["id"]
                current_data["fraud_result"] = fraud_result
                genuine_discounts.append(current_data)

        # Ранжируем и публикуем лучшие
        if genuine_discounts:
            ranked = await ranker.rank_products(genuine_discounts)
            # Публикуем top-5
            for item in ranked[:5]:
                try:
                    # Получаем отзывы для суммаризации
                    reviews: list[str] = []
                    ext_id = item.get("article_id") or item.get("product_id", "")
                    mp = item.get("marketplace", "")
                    if mp == "wildberries":
                        reviews = await wb_parser.fetch_reviews(ext_id)
                    elif mp == "ozon":
                        reviews = await ozon_parser.fetch_reviews(ext_id)

                    review_summary = await reviews_summarizer.summarize(reviews)

                    # Генерируем пост
                    discount_info = {
                        "discount_percent": item.get("discount", 0),
                        "is_fraud": False,
                    }
                    post_text = await post_gen.generate_post(
                        item, discount_info, review_summary
                    )

                    # Сохраняем пост в БД
                    await add_post(
                        product_id=item.get("product_db_id", 0),
                        channel_id=settings.telegram_channel_id,
                        text=post_text,
                    )
                    logger.info("Сгенерирован пост для товара: %s", item.get("name", ""))
                except Exception as e:
                    logger.error("Ошибка генерации поста: %s", e)

        logger.info("Парсинг завершен. Обработано %d товаров.", len(products))
    finally:
        await wb_parser.close()
        await ozon_parser.close()


async def publish_digests_job() -> None:
    """Публикация дайджестов: 'Top-10 падений цен', 'Исторические минимумы'.

    Запускается раз в день.
    """
    logger.info("Запуск задачи публикации дайджестов...")

    post_gen = PostGenerator()

    try:
        # Получаем товары с наибольшим снижением цены за день
        top_drops = await _get_top_price_drops(limit=10)
        if top_drops:
            logger.info("Найдено %d товаров для дайджеста 'Top-10'", len(top_drops))

        # Исторические минимумы
        historical_mins = await _get_historical_minimums(limit=10)
        if historical_mins:
            logger.info("Найдено %d товаров с историческими минимумами", len(historical_mins))

    except Exception as e:
        logger.error("Ошибка публикации дайджеста: %s", e)


async def cleanup_old_data_job() -> None:
    """Очистка старых записей из price_history (старше 90 дней).

    Запускается раз в неделю.
    """
    logger.info("Запуск задачи очистки старых данных...")

    cutoff_date = (datetime.now() - timedelta(days=90)).isoformat()

    try:
        db = await aiosqlite.connect(settings.db_path)
        try:
            await db.execute(
                "DELETE FROM price_history WHERE timestamp < ?",
                (cutoff_date,),
            )
            await db.commit()
            logger.info("Очистка записей старше %s завершена", cutoff_date)
        finally:
            await db.close()
    except Exception as e:
        logger.error("Ошибка очистки данных: %s", e)


# --- Вспомогательные функции ---


async def _get_tracked_products() -> list[dict[str, Any]]:
    """Получить все отслеживаемые товары из БД."""
    try:
        db = await aiosqlite.connect(settings.db_path)
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute("SELECT * FROM products")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()
    except Exception as e:
        logger.error("Ошибка получения товаров: %s", e)
        return []


async def _get_top_price_drops(limit: int = 10) -> list[dict[str, Any]]:
    """Получить товары с наибольшим снижением цены за последние 24 часа."""
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    try:
        db = await aiosqlite.connect(settings.db_path)
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute(
                """
                SELECT p.*, ph.price, ph.old_price, ph.discount_percent
                FROM price_history ph
                JOIN products p ON p.id = ph.product_id
                WHERE ph.timestamp > ? AND ph.is_fraud = 0 AND ph.discount_percent > 0
                ORDER BY ph.discount_percent DESC
                LIMIT ?
                """,
                (cutoff, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()
    except Exception as e:
        logger.error("Ошибка получения top drops: %s", e)
        return []


async def _get_historical_minimums(limit: int = 10) -> list[dict[str, Any]]:
    """Получить товары, достигшие исторического минимума цены."""
    try:
        db = await aiosqlite.connect(settings.db_path)
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute(
                """
                SELECT p.*, ph.price as current_price,
                       (SELECT MIN(ph2.price) FROM price_history ph2 WHERE ph2.product_id = p.id) as min_price
                FROM products p
                JOIN price_history ph ON ph.product_id = p.id
                WHERE ph.id = (SELECT MAX(ph3.id) FROM price_history ph3 WHERE ph3.product_id = p.id)
                HAVING current_price <= min_price
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()
    except Exception as e:
        logger.error("Ошибка получения исторических минимумов: %s", e)
        return []
