"""Модуль локализации промптов AI-агентства."""

import logging
from typing import Tuple, Dict, Optional

import config
from services import SERVICES, get_service
from models import ServiceType

logger = logging.getLogger(__name__)

# Попытка импорта openai (graceful)
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# In-memory кеш переведённых промптов: {(service_type, lang): (system_prompt, user_prompt_template)}
_prompt_cache: Dict[Tuple[str, str], Tuple[str, str]] = {}

# Lazy-singleton клиент
_client: Optional[object] = None


def _get_client():
    """Получить или создать OpenAI клиент."""
    global _client
    if _client is None and AsyncOpenAI is not None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


async def _translate_prompt(text: str, target_lang: str) -> str:
    """Перевести текст промпта на указанный язык через LLM."""
    client = _get_client()
    if client is None:
        return text  # Возвращаем оригинал если LLM недоступен

    lang_name = "English" if target_lang == "en" else target_lang
    try:
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a translator. Translate the following system prompt "
                        f"to {lang_name}. Keep the same meaning, tone, and instructions. "
                        f"Return only the translated text without explanations."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Ошибка перевода промпта: %s", e)
        return text


async def _cache_to_db(service_type: str, lang: str, system_prompt: str, user_prompt: str) -> None:
    """Сохранить перевод в БД кеш."""
    try:
        import aiosqlite
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO prompt_cache
                   (service_type, lang, system_prompt, user_prompt, cached_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (service_type, lang, system_prompt, user_prompt),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка сохранения prompt_cache: %s", e)


async def _load_from_db(service_type: str, lang: str) -> Optional[Tuple[str, str]]:
    """Загрузить перевод из БД кеша."""
    try:
        import aiosqlite
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT system_prompt, user_prompt FROM prompt_cache WHERE service_type = ? AND lang = ?",
                (service_type, lang),
            )
            row = await cursor.fetchone()
            if row:
                return (row[0], row[1])
    except Exception as e:
        logger.debug("Ошибка загрузки prompt_cache: %s", e)
    return None


async def get_localized_prompts(
    service_type: str, lang: str
) -> Tuple[str, str]:
    """
    Получить локализованные промпты для услуги.

    Если язык 'ru' - возвращает оригинальные промпты.
    Для других языков - переводит и кеширует.

    Args:
        service_type: тип услуги (значение ServiceType)
        lang: код языка ('ru', 'en', etc.)

    Returns:
        Кортеж (system_prompt, user_prompt_template)
    """
    # Для русского языка возвращаем оригинал
    if lang == "ru":
        try:
            stype = ServiceType(service_type)
            service = get_service(stype)
            return (service.system_prompt, service.user_prompt_template)
        except (ValueError, KeyError):
            return ("", "")

    # Проверяем in-memory кеш
    cache_key = (service_type, lang)
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    # Проверяем БД кеш
    db_cached = await _load_from_db(service_type, lang)
    if db_cached:
        _prompt_cache[cache_key] = db_cached
        return db_cached

    # Получаем оригинальные промпты
    try:
        stype = ServiceType(service_type)
        service = get_service(stype)
    except (ValueError, KeyError):
        return ("", "")

    # Переводим
    translated_system = await _translate_prompt(service.system_prompt, lang)
    translated_user = await _translate_prompt(service.user_prompt_template, lang)

    # Кешируем
    _prompt_cache[cache_key] = (translated_system, translated_user)
    await _cache_to_db(service_type, lang, translated_system, translated_user)

    return (translated_system, translated_user)


def clear_cache() -> None:
    """Очистить in-memory кеш промптов."""
    _prompt_cache.clear()
