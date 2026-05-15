"""Парсер лидов с FL.ru: поиск проектов по ключевым словам с human-like откликами."""

import asyncio
import logging
import random
import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import quote

import aiohttp
import aiosqlite

import config

logger = logging.getLogger(__name__)

# Graceful imports
try:
    import llm_router as _llm_router
except ImportError:
    _llm_router = None

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Lazy-singleton OpenAI клиент
_openai_client: Optional[object] = None

# In-memory daily counter
_daily_responses: int = 0
_daily_responses_date: Optional[date] = None


def _get_openai_client():
    """Получить или создать OpenAI клиент."""
    global _openai_client
    if _openai_client is None and AsyncOpenAI is not None:
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def _is_working_hours() -> bool:
    """Check if current time is within working hours."""
    now = datetime.now()
    return config.KWORK_WORK_HOURS_START <= now.hour < config.KWORK_WORK_HOURS_END


def _check_daily_limit() -> bool:
    """Check if daily FL.ru response limit is not exceeded."""
    global _daily_responses, _daily_responses_date

    today = date.today()
    if _daily_responses_date != today:
        _daily_responses = 0
        _daily_responses_date = today

    return _daily_responses < config.FL_MAX_DAILY_RESPONSES


def _increment_daily_counter() -> None:
    """Increment daily response counter."""
    global _daily_responses, _daily_responses_date

    today = date.today()
    if _daily_responses_date != today:
        _daily_responses = 0
        _daily_responses_date = today

    _daily_responses += 1


async def init_fl_leads_table() -> None:
    """Создать таблицу fl_leads если не существует."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fl_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                title TEXT,
                url TEXT,
                parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def _is_fl_lead_seen(external_id: str) -> bool:
    """Проверить, был ли лид FL.ru уже обработан."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM fl_leads WHERE external_id = ?",
            (external_id,),
        )
        row = await cursor.fetchone()
        return row is not None


async def _mark_fl_lead_seen(external_id: str, title: str, url: str) -> None:
    """Отметить лид FL.ru как обработанный."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO fl_leads (external_id, title, url) VALUES (?, ?, ?)",
            (external_id, title, url),
        )
        await db.commit()


async def parse_fl_orders(keywords: List[str]) -> List[dict]:
    """
    Парсить проекты FL.ru по ключевым словам.

    Загружает страницу проектов и извлекает данные.
    Возвращает список словарей: id, title, description, link, budget.
    """
    all_entries = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    for keyword in keywords:
        url = f"https://www.fl.ru/projects/?action=search&search_string={quote(keyword)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        logger.warning("FL.ru fetch failed (status=%d) for '%s'", resp.status, keyword)
                        continue
                    html = await resp.text()

            # Extract project links and titles
            # FL.ru project links: /projects/XXXXXX/...
            project_links = re.findall(
                r'href="(/projects/\d+/[^"]*)"', html
            )
            titles = re.findall(
                r'class="[^"]*b-post__title[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', html
            )
            descriptions = re.findall(
                r'class="[^"]*b-post__body[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL
            )

            for i, link in enumerate(project_links[:20]):
                full_url = f"https://www.fl.ru{link}"
                title = titles[i].strip() if i < len(titles) else ""
                desc = ""
                if i < len(descriptions):
                    # Strip HTML tags from description
                    desc = re.sub(r'<[^>]+>', '', descriptions[i]).strip()[:300]

                entry_id = link  # unique project path
                all_entries.append({
                    "id": entry_id,
                    "title": title,
                    "description": desc,
                    "link": full_url,
                    "budget": "",
                })

            # Anti-detect: small delay between keyword searches
            await asyncio.sleep(random.uniform(2, 5))

        except Exception as e:
            logger.warning("Ошибка парсинга FL.ru для '%s': %s", keyword, e)

    return all_entries


async def generate_fl_response(order_info: dict) -> str:
    """
    Генерация отклика для FL.ru проекта через AI.

    Уникальный текст, 50-150 слов, случайный тон.
    """
    title = order_info.get("title", "Проект")
    description = order_info.get("description", "")[:500]

    tone = random.choice(["formal", "informal", "friendly"])
    tone_map = {
        "formal": "деловой вежливый тон, на 'Вы'",
        "informal": "дружелюбный неформальный тон, на 'ты'",
        "friendly": "теплый профессиональный тон",
    }
    word_count = random.randint(50, 150)

    prompt = (
        f"Напиши уникальный отклик на проект на бирже FL.ru.\n\n"
        f"Проект: {title}\n"
        f"Описание: {description}\n\n"
        f"Требования:\n"
        f"- Тон: {tone_map[tone]}\n"
        f"- Длина: ~{word_count} слов\n"
        f"- Задай уточняющий вопрос по проекту\n"
        f"- Упомяни опыт в копирайтинге/текстах (2-3 года)\n"
        f"- Будь оригинален, избегай шаблонов\n"
        f"- Заверши предложением обсудить условия\n"
    )

    messages = [
        {"role": "system", "content": "Ты опытный фрилансер-копирайтер на FL.ru."},
        {"role": "user", "content": prompt},
    ]

    # Try llm_router
    if _llm_router is not None:
        try:
            result = await _llm_router.generate(messages, temperature=0.8, max_tokens=500)
            if result:
                return result
        except Exception as e:
            logger.warning("llm_router error in FL response: %s", e)

    # Fallback to OpenAI
    client = _get_openai_client()
    if client is not None and config.OPENAI_API_KEY:
        try:
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("OpenAI error in FL response: %s", e)

    # Template fallback
    return (
        f"Здравствуйте! Заинтересовал ваш проект \"{title}\".\n\n"
        f"Работаю с текстами более 3 лет, есть опыт в подобных задачах. "
        f"Подскажите, какой объем и сроки вы рассматриваете?\n\n"
        f"Готов обсудить детали и приступить к работе!"
    )


async def _submit_fl_response(order_info: dict, response_text: str) -> bool:
    """
    Stub: отправить отклик на проект FL.ru.

    В продакшене требует авторизации через cookies/session.
    """
    order_url = order_info.get("link", "")
    if not order_url:
        return False

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"message": response_text}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": order_url,
            }
            respond_url = order_url.rstrip("/") + "/respond/"
            async with session.post(
                respond_url,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201, 302):
                    logger.info("FL.ru отклик отправлен: %s", order_url)
                    return True
                else:
                    logger.warning("FL.ru отклик не отправлен (status=%d): %s", resp.status, order_url)
                    return False
    except Exception as e:
        logger.warning("Ошибка отправки отклика FL.ru: %s", e)
        return False


async def check_new_fl_leads(bot) -> None:
    """
    Основная функция проверки новых лидов на FL.ru.

    Human-like: working hours, daily limit, random delays.
    """
    # Working hours check
    if not _is_working_hours():
        logger.debug("FL parser: outside working hours, skipping")
        return

    # Get keywords (FL_KEYWORDS or fallback to KWORK_KEYWORDS)
    keywords_str = config.FL_KEYWORDS or config.KWORK_KEYWORDS
    if not keywords_str:
        return

    keywords = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
    if not keywords:
        return

    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        return

    # Initialize table
    await init_fl_leads_table()

    entries = await parse_fl_orders(keywords)
    new_count = 0

    for entry in entries:
        external_id = entry["id"]
        if not external_id:
            continue

        if await _is_fl_lead_seen(external_id):
            continue

        # Check daily limit
        if not _check_daily_limit():
            logger.info("FL parser: daily limit reached (%d), stopping", _daily_responses)
            break

        # Mark as seen
        await _mark_fl_lead_seen(external_id, entry["title"], entry["link"])

        # Human-like delay (3-15 min)
        delay = random.uniform(180, 900)
        logger.debug("FL parser: waiting %.0f seconds before responding", delay)
        await asyncio.sleep(delay)

        # Re-check working hours
        if not _is_working_hours():
            break

        # Generate response
        response_text = await generate_fl_response(entry)

        if config.AUTO_RESPOND_LEADS:
            # Auto-respond mode
            success = await _submit_fl_response(entry, response_text)
            _increment_daily_counter()

            status_emoji = "\u2705" if success else "\u274c"
            notification = (
                f"{status_emoji} <b>FL.ru автоотклик</b>\n\n"
                f"<b>Проект:</b> {entry['title']}\n"
                f"<b>Ссылка:</b> {entry['link']}\n\n"
                f"<b>Текст:</b>\n<pre>{response_text[:500]}</pre>"
            )
            try:
                await bot.send_message(chat_id=admin_id, text=notification, parse_mode="HTML")
            except Exception as e:
                logger.debug("Не удалось уведомить админа о FL.ru отклике: %s", e)
            new_count += 1
        else:
            # Notify admin mode
            notification = (
                f"\U0001f4e8 <b>Новый лид на FL.ru</b>\n\n"
                f"<b>Проект:</b> {entry['title']}\n"
                f"<b>Описание:</b> {entry['description'][:300]}\n"
                f"<b>Ссылка:</b> {entry['link']}\n\n"
                f"<b>Шаблон ответа:</b>\n<pre>{response_text}</pre>"
            )
            try:
                await bot.send_message(chat_id=admin_id, text=notification, parse_mode="HTML")
                _increment_daily_counter()
                new_count += 1
            except Exception as e:
                logger.warning("Не удалось отправить FL.ru уведомление: %s", e)

    if new_count:
        logger.info("FL parser: обработано %d новых лидов", new_count)
