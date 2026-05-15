"""Парсер лидов с Kwork RSS: поиск заказов по ключевым словам и уведомление админа."""

import logging
from typing import List, Optional
from urllib.parse import quote

import aiosqlite
import feedparser

import config

logger = logging.getLogger(__name__)


async def init_leads_table() -> None:
    """Создать таблицу parsed_leads если не существует."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS parsed_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                title TEXT,
                url TEXT,
                parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def _is_lead_seen(external_id: str) -> bool:
    """Проверить, был ли лид уже обработан."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM parsed_leads WHERE external_id = ?",
            (external_id,),
        )
        row = await cursor.fetchone()
        return row is not None


async def _mark_lead_seen(external_id: str, title: str, url: str) -> None:
    """Отметить лид как обработанный."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO parsed_leads (external_id, title, url) VALUES (?, ?, ?)",
            (external_id, title, url),
        )
        await db.commit()


async def parse_kwork_orders(keywords: List[str]) -> List[dict]:
    """
    Парсить RSS Kwork по списку ключевых слов.

    Возвращает список словарей с полями: id, title, description, link, budget.
    """
    all_entries = []
    for keyword in keywords:
        url = f"https://kwork.ru/projects?c=all&keyword={quote(keyword)}"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
                all_entries.append({
                    "id": entry_id,
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "budget": entry.get("budget", ""),
                })
        except Exception as e:
            logger.warning("Ошибка парсинга Kwork RSS для '%s': %s", keyword, e)
    return all_entries


async def generate_response(order_info: dict, service_type: str) -> str:
    """
    Создать шаблон профессионального ответа для заказа.

    Возвращает готовый текст ответа.
    """
    title = order_info.get("title", "Заказ")
    description = order_info.get("description", "")[:200]
    response = (
        f"Здравствуйте! Готов выполнить ваш заказ \"{title}\".\n\n"
        f"Имею опыт в {service_type}. Работаю с AI-инструментами для максимального качества.\n\n"
        f"Сроки: 1-2 дня. Гарантирую уникальность и соответствие ТЗ.\n\n"
        f"Буду рад сотрудничеству!"
    )
    return response


async def check_new_leads(bot) -> None:
    """
    Основная функция проверки новых лидов:
    парсит заказы, фильтрует новые, отправляет уведомление админу.
    """
    keywords_str = config.KWORK_KEYWORDS
    if not keywords_str:
        return

    keywords = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
    if not keywords:
        return

    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        return

    entries = await parse_kwork_orders(keywords)
    new_count = 0

    for entry in entries:
        external_id = entry["id"]
        if not external_id:
            continue

        if await _is_lead_seen(external_id):
            continue

        # Новый лид - сохраняем и уведомляем
        await _mark_lead_seen(external_id, entry["title"], entry["link"])

        # Генерируем ответ
        response_text = await generate_response(entry, "копирайтинг")

        # Уведомление админу
        notification = (
            f"\U0001f4e8 <b>Новый лид на Kwork</b>\n\n"
            f"<b>Название:</b> {entry['title']}\n"
            f"<b>Описание:</b> {entry['description'][:300]}\n"
            f"<b>Ссылка:</b> {entry['link']}\n\n"
            f"<b>Шаблон ответа:</b>\n<pre>{response_text}</pre>"
        )

        try:
            await bot.send_message(
                chat_id=admin_id,
                text=notification,
                parse_mode="HTML",
            )
            new_count += 1
        except Exception as e:
            logger.warning("Не удалось отправить уведомление о лиде: %s", e)

    if new_count:
        logger.info("Lead parser: отправлено %d новых лидов", new_count)
