"""Парсер лидов с Kwork: поиск заказов по ключевым словам, human-like автоотклик."""

import asyncio
import json
import logging
import os
import random
from datetime import datetime, date
from typing import List, Optional
from urllib.parse import quote

import aiohttp
import aiosqlite
import feedparser

import config

logger = logging.getLogger(__name__)

# Graceful imports
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    import llm_router as _llm_router
except ImportError:
    _llm_router = None

# Lazy-singleton OpenAI клиент
_openai_client: Optional[object] = None

# In-memory daily counter (reset daily)
_daily_responses: int = 0
_daily_responses_date: Optional[date] = None

# State file for warmup tracking
KWORK_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kwork_state.json")


def _get_openai_client():
    """Получить или создать OpenAI клиент."""
    global _openai_client
    if _openai_client is None and AsyncOpenAI is not None:
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def _load_kwork_state() -> dict:
    """Load kwork state from JSON file (registration date etc)."""
    try:
        if os.path.exists(KWORK_STATE_FILE):
            with open(KWORK_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Error loading kwork_state.json: %s", e)
    return {}


def _save_kwork_state(state: dict) -> None:
    """Save kwork state to JSON file."""
    try:
        with open(KWORK_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning("Error saving kwork_state.json: %s", e)


def _get_registration_date() -> date:
    """Get or set registration date from state file."""
    state = _load_kwork_state()
    if "registration_date" in state:
        return date.fromisoformat(state["registration_date"])
    # First run - set today as registration date
    today = date.today()
    state["registration_date"] = today.isoformat()
    _save_kwork_state(state)
    return today


def _get_warmup_limit() -> int:
    """Get daily response limit based on warmup period."""
    reg_date = _get_registration_date()
    days_since = (date.today() - reg_date).days

    warmup_days = config.KWORK_WARMUP_DAYS
    half_warmup = warmup_days // 2  # first half: strict limit

    if days_since < half_warmup:
        return 2  # First week: max 2/day
    elif days_since < warmup_days:
        return 4  # Second week: max 4/day
    else:
        return config.KWORK_MAX_DAILY_RESPONSES  # Full limit


def _is_working_hours() -> bool:
    """Check if current time is within working hours."""
    now = datetime.now()
    return config.KWORK_WORK_HOURS_START <= now.hour < config.KWORK_WORK_HOURS_END


def _check_daily_limit() -> bool:
    """Check if daily response limit is not exceeded. Returns True if can respond."""
    global _daily_responses, _daily_responses_date

    today = date.today()
    if _daily_responses_date != today:
        _daily_responses = 0
        _daily_responses_date = today

    limit = _get_warmup_limit()
    return _daily_responses < limit


def _increment_daily_counter() -> None:
    """Increment daily response counter."""
    global _daily_responses, _daily_responses_date

    today = date.today()
    if _daily_responses_date != today:
        _daily_responses = 0
        _daily_responses_date = today

    _daily_responses += 1


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
    Создать уникальный human-like отклик для заказа.

    AI генерирует текст с:
    - Именем клиента (если доступно)
    - Вопросом по ТЗ
    - Релевантным опытом
    - 50-150 слов
    - Случайный тон (формальный/неформальный)
    """
    title = order_info.get("title", "Заказ")
    description = order_info.get("description", "")[:500]
    customer_name = order_info.get("customer_name", "")

    # Random tone selection
    tone = random.choice(["formal", "informal", "friendly"])
    tone_instruction = {
        "formal": "Используй деловой, вежливый тон. Обращайся на 'Вы'.",
        "informal": "Используй дружелюбный неформальный тон. Обращайся на 'ты'.",
        "friendly": "Используй теплый профессиональный тон, не слишком официальный.",
    }[tone]

    word_count = random.randint(50, 150)

    prompt = (
        f"Напиши уникальный отклик фрилансера на заказ.\n\n"
        f"Заказ: {title}\n"
        f"Описание: {description}\n"
    )
    if customer_name:
        prompt += f"Имя заказчика: {customer_name}\n"
    prompt += (
        f"Специализация: {service_type}\n\n"
        f"Требования:\n"
        f"- {tone_instruction}\n"
        f"- Длина: примерно {word_count} слов\n"
        f"- Задай 1 уточняющий вопрос по ТЗ\n"
        f"- Кратко упомяни релевантный опыт (2-3 года в нише)\n"
        f"- НЕ используй шаблонные фразы вроде 'Уважаемый заказчик'\n"
        f"- Не копируй стандартные отклики, будь оригинален\n"
        f"- Заверши предложением обсудить детали\n"
    )

    messages = [
        {"role": "system", "content": "Ты опытный фрилансер. Пишешь живые, человечные отклики на заказы."},
        {"role": "user", "content": prompt},
    ]

    # Try llm_router first
    if _llm_router is not None:
        try:
            result = await _llm_router.generate(messages, temperature=0.8, max_tokens=500)
            if result:
                return result
        except Exception as e:
            logger.warning("llm_router error in generate_response: %s", e)

    # Fallback to direct OpenAI
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
            logger.warning("Ошибка генерации отклика через AI: %s", e)

    # Fallback шаблон
    name_part = f" {customer_name}," if customer_name else ""
    response_text = (
        f"Здравствуйте{name_part}! Готов взяться за ваш проект \"{title}\".\n\n"
        f"Работаю в сфере {service_type} более 3 лет. "
        f"Подскажите, есть ли примеры желаемого результата?\n\n"
        f"Сроки: 1-2 дня. Давайте обсудим детали!"
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
    Основная функция проверки новых лидов с human-like поведением.

    Human-like features:
    - Working hours check (9:00-22:00 by default)
    - Daily response limit with warmup
    - Random delay 3-15 min before each response

    Если AUTO_RESPOND_LEADS=True: формирует отклик через AI и отправляет на Kwork.
    Если False: уведомляет админа с шаблоном ответа (поведение по умолчанию).
    """
    # Working hours check
    if not _is_working_hours():
        logger.debug("Lead parser: outside working hours, skipping")
        return

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

        # Check daily limit before responding
        if not _check_daily_limit():
            logger.info("Lead parser: daily limit reached (%d), stopping", _daily_responses)
            break

        # Новый лид - сохраняем
        await _mark_lead_seen(external_id, entry["title"], entry["link"])

        # Human-like random delay (3-15 minutes)
        delay = random.uniform(180, 900)
        logger.debug("Lead parser: waiting %.0f seconds before responding", delay)
        await asyncio.sleep(delay)

        # Re-check working hours after delay
        if not _is_working_hours():
            logger.debug("Lead parser: left working hours after delay, stopping")
            break

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
            # Increment daily counter
            _increment_daily_counter()

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
                _increment_daily_counter()
                new_count += 1
            except Exception as e:
                logger.warning("Не удалось отправить уведомление о лиде: %s", e)

    if new_count:
        logger.info(
            "Lead parser: обработано %d новых лидов (auto_respond=%s)",
            new_count, config.AUTO_RESPOND_LEADS,
        )
