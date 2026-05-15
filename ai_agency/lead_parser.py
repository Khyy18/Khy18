"""Парсер лидов с Kwork: поиск заказов по ключевым словам и уведомление/автоотклик."""

import logging
from typing import List, Optional
from urllib.parse import quote

import aiohttp
import aiosqlite
import feedparser

import config

logger = logging.getLogger(__name__)

# Попытка импорта openai (graceful)
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Lazy-singleton OpenAI клиент
_openai_client: Optional[object] = None


def _get_openai_client():
    """Получить или создать OpenAI клиент."""
    global _openai_client
    if _openai_client is None and AsyncOpenAI is not None:
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


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
    Парсить заказы Kwork по списку ключевых слов.

    Пытается использовать RSS-формат (с параметром rss=1).
    Если RSS не вернул записей, делает HTTP-запрос к странице проектов
    и пытается извлечь данные.

    Возвращает список словарей с полями: id, title, description, link, budget.
    """
    all_entries = []
    for keyword in keywords:
        # Используем RSS URL формат Kwork
        rss_url = f"https://kwork.ru/projects?c=all&attr=s&keyword={quote(keyword)}&rss=1"
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                for entry in feed.entries:
                    entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
                    all_entries.append({
                        "id": entry_id,
                        "title": entry.get("title", ""),
                        "description": entry.get("summary", entry.get("description", "")),
                        "link": entry.get("link", ""),
                        "budget": entry.get("budget", ""),
                    })
            else:
                # RSS не вернул записей - пробуем HTML страницу
                page_url = f"https://kwork.ru/projects?c=all&attr=s&keyword={quote(keyword)}"
                await _parse_kwork_html(page_url, all_entries)
        except Exception as e:
            logger.warning("Ошибка парсинга Kwork для '%s': %s", keyword, e)
    return all_entries


async def _parse_kwork_html(url: str, entries: List[dict]) -> None:
    """
    Fallback: загрузить HTML страницу проектов Kwork и извлечь базовые данные.
    Используется если RSS не вернул записей.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning("Kwork HTML fetch failed with status %d", resp.status)
                    return
                html_text = await resp.text()

        # Извлекаем ссылки на проекты из HTML (простой regex-подход)
        import re
        # Ищем ссылки на проекты вида /projects/XXXXX/...
        project_links = re.findall(
            r'href="(https://kwork\.ru/projects/\d+/[^"]+)"', html_text
        )
        # Ищем заголовки проектов
        titles = re.findall(
            r'class="[^"]*wants-card__header-title[^"]*"[^>]*>([^<]+)<', html_text
        )

        for i, link in enumerate(project_links[:20]):  # ограничиваем 20 записями
            title = titles[i] if i < len(titles) else ""
            entry_id = link
            entries.append({
                "id": entry_id,
                "title": title.strip(),
                "description": "",
                "link": link,
                "budget": "",
            })
    except Exception as e:
        logger.warning("Ошибка парсинга Kwork HTML: %s", e)


async def generate_response(order_info: dict, service_type: str) -> str:
    """
    Создать профессиональный отклик для заказа.

    Если доступен OpenAI - генерирует через AI под конкретный заказ.
    Иначе - использует шаблон.
    """
    title = order_info.get("title", "Заказ")
    description = order_info.get("description", "")[:500]

    client = _get_openai_client()
    if client is not None and config.OPENAI_API_KEY:
        try:
            prompt = (
                f"Напиши профессиональный отклик фрилансера на заказ на бирже Kwork.\n\n"
                f"Заказ: {title}\n"
                f"Описание: {description}\n"
                f"Специализация: {service_type}\n\n"
                f"Требования к отклику:\n"
                f"- Короткий (3-5 предложений)\n"
                f"- Профессиональный тон\n"
                f"- Упомяни релевантный опыт\n"
                f"- Укажи сроки (1-2 дня)\n"
                f"- Заверши призывом к действию\n"
                f"- Не используй формальное обращение 'Уважаемый'\n"
            )
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "Ты опытный фрилансер, пишешь отклики на заказы."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("Ошибка генерации отклика через AI: %s", e)

    # Fallback шаблон
    response_text = (
        f"Здравствуйте! Готов выполнить ваш заказ \"{title}\".\n\n"
        f"Имею опыт в {service_type}. Работаю с AI-инструментами для максимального качества.\n\n"
        f"Сроки: 1-2 дня. Гарантирую уникальность и соответствие ТЗ.\n\n"
        f"Буду рад сотрудничеству!"
    )
    return response_text


async def _submit_kwork_response(order_info: dict, response_text: str) -> bool:
    """
    Отправить автоотклик на заказ Kwork через HTTP POST.

    Имитирует отправку отклика. В продакшене нужно авторизоваться
    через cookies/token и отправить POST на форму отклика.
    """
    order_url = order_info.get("link", "")
    if not order_url:
        return False

    try:
        async with aiohttp.ClientSession() as session:
            # POST отклик на Kwork (структура формы отклика)
            payload = {
                "message": response_text,
                "price": "",  # Цена по умолчанию из кворка
                "duration": "2",  # 2 дня
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": order_url,
            }
            # Отправляем POST на URL отклика
            respond_url = order_url.rstrip("/") + "/respond"
            async with session.post(
                respond_url,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201, 302):
                    logger.info("Автоотклик отправлен на: %s", order_url)
                    return True
                else:
                    logger.warning(
                        "Автоотклик не отправлен (status=%d): %s", resp.status, order_url
                    )
                    return False
    except Exception as e:
        logger.warning("Ошибка отправки автоотклика: %s", e)
        return False


async def check_new_leads(bot) -> None:
    """
    Основная функция проверки новых лидов.

    Если AUTO_RESPOND_LEADS=True: формирует отклик через AI и отправляет на Kwork.
    Если False: уведомляет админа с шаблоном ответа (поведение по умолчанию).
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

        # Новый лид - сохраняем
        await _mark_lead_seen(external_id, entry["title"], entry["link"])

        # Генерируем отклик
        response_text = await generate_response(entry, "копирайтинг")

        if config.AUTO_RESPOND_LEADS:
            # Режим автоотклика: отправляем на Kwork и логируем
            success = await _submit_kwork_response(entry, response_text)
            status_emoji = "\u2705" if success else "\u274c"
            logger.info(
                "AUTO_RESPOND [%s]: %s | %s",
                "OK" if success else "FAIL",
                entry["title"],
                entry["link"],
            )
            # Уведомляем админа о факте автоотклика
            notification = (
                f"{status_emoji} <b>Автоотклик отправлен</b>\n\n"
                f"<b>Заказ:</b> {entry['title']}\n"
                f"<b>Ссылка:</b> {entry['link']}\n\n"
                f"<b>Текст отклика:</b>\n<pre>{response_text[:500]}</pre>"
            )
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=notification,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.debug("Не удалось уведомить админа об автоотклике: %s", e)
            new_count += 1
        else:
            # Режим уведомления: отправляем шаблон админу для ручной отправки
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
        logger.info("Lead parser: обработано %d новых лидов (auto_respond=%s)", new_count, config.AUTO_RESPOND_LEADS)
