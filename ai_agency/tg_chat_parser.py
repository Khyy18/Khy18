"""Telegram chat monitor: поиск заказов в чатах по ключевым словам с AI-ответами."""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)

# Graceful import of pyrogram
try:
    from pyrogram import Client, filters
    from pyrogram.types import Message
    _pyrogram_available = True
except ImportError:
    Client = None
    filters = None
    Message = None
    _pyrogram_available = False

# Graceful import of llm_router
try:
    import llm_router as _llm_router
except ImportError:
    _llm_router = None

# Graceful import of OpenAI
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Keywords to monitor
MONITOR_KEYWORDS: List[str] = [
    "ищу копирайтера",
    "нужен текст",
    "кто напишет",
    "требуется автор",
    "нужен автор",
    "ищу автора",
]

# Anti-spam tracking: {chat_id: [timestamp, ...]}
_response_timestamps: Dict[int, List[float]] = defaultdict(list)

# Lazy singleton clients
_openai_client: Optional[object] = None
_pyrogram_client: Optional[object] = None


def _get_openai_client():
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None and AsyncOpenAI is not None and config.OPENAI_API_KEY:
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def _get_pyrogram_client():
    """Get or create pyrogram userbot client."""
    global _pyrogram_client
    if _pyrogram_client is not None:
        return _pyrogram_client

    if not _pyrogram_available:
        return None

    if not config.TELEGRAM_USERBOT_SESSION:
        return None

    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        return None

    try:
        _pyrogram_client = Client(
            config.TELEGRAM_USERBOT_SESSION,
            api_id=int(config.TELEGRAM_API_ID),
            api_hash=config.TELEGRAM_API_HASH,
        )
        return _pyrogram_client
    except Exception as e:
        logger.warning("Failed to create pyrogram client: %s", e)
        return None


def _get_monitor_chats() -> List[int]:
    """Get list of chat IDs to monitor from config."""
    chats_str = config.TG_MONITOR_CHATS
    if not chats_str:
        return []
    try:
        return [int(c.strip()) for c in chats_str.split(",") if c.strip()]
    except ValueError:
        logger.warning("Invalid TG_MONITOR_CHATS format: %s", chats_str)
        return []


def _can_respond_in_chat(chat_id: int) -> bool:
    """Check anti-spam: max N responses per hour per chat."""
    now = time.time()
    hour_ago = now - 3600

    # Clean old timestamps
    _response_timestamps[chat_id] = [
        ts for ts in _response_timestamps[chat_id] if ts > hour_ago
    ]

    return len(_response_timestamps[chat_id]) < config.TG_MAX_RESPONSES_PER_HOUR


def _record_response(chat_id: int) -> None:
    """Record a response timestamp for anti-spam tracking."""
    _response_timestamps[chat_id].append(time.time())


def _message_matches_keywords(text: str) -> bool:
    """Check if message text contains any monitored keywords."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in MONITOR_KEYWORDS)


async def generate_contextual_response(message_text: str) -> str:
    """
    Generate a contextual, helpful response (not an ad).

    Style: helpful, brief, suggests to DM for details.
    """
    prompt = (
        f"Пользователь в чате написал: \"{message_text}\"\n\n"
        f"Напиши короткий (1-2 предложения) ответ от лица копирайтера, который может помочь.\n"
        f"Требования:\n"
        f"- НЕ рекламируй себя напрямую\n"
        f"- Будь полезен и дружелюбен\n"
        f"- Предложи написать в ЛС для обсуждения\n"
        f"- Максимум 2 предложения\n"
        f"- Пример стиля: 'Могу помочь с этим, пишите в ЛС - обсудим детали'\n"
    )

    messages = [
        {"role": "system", "content": "Ты копирайтер, коротко отвечаешь в чатах. Не рекламируй, просто предложи помощь."},
        {"role": "user", "content": prompt},
    ]

    # Try llm_router
    if _llm_router is not None:
        try:
            result = await _llm_router.generate(messages, temperature=0.7, max_tokens=100)
            if result:
                return result
        except Exception as e:
            logger.warning("llm_router error in tg_chat response: %s", e)

    # Fallback to OpenAI
    client = _get_openai_client()
    if client is not None:
        try:
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=100,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("OpenAI error in tg_chat response: %s", e)

    # Template fallback
    return "Могу помочь с этим, пишите в ЛС - обсудим детали!"


def is_configured() -> bool:
    """Check if TG chat parser is properly configured and can run."""
    if not _pyrogram_available:
        logger.debug("tg_chat_parser: pyrogram not available")
        return False
    if not config.TELEGRAM_USERBOT_SESSION:
        logger.debug("tg_chat_parser: TELEGRAM_USERBOT_SESSION not set")
        return False
    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        logger.debug("tg_chat_parser: TELEGRAM_API_ID/HASH not set")
        return False
    if not _get_monitor_chats():
        logger.debug("tg_chat_parser: no chats to monitor (TG_MONITOR_CHATS empty)")
        return False
    return True


async def _process_message(client_instance, message) -> None:
    """Process a single message from monitored chat."""
    if not message or not message.text:
        return

    chat_id = message.chat.id

    # Check if message matches keywords
    if not _message_matches_keywords(message.text):
        return

    # Anti-spam check
    if not _can_respond_in_chat(chat_id):
        logger.debug("tg_chat_parser: anti-spam limit for chat %d", chat_id)
        return

    # Generate and send response
    try:
        response_text = await generate_contextual_response(message.text)
        await message.reply(response_text)
        _record_response(chat_id)
        logger.info("tg_chat_parser: responded in chat %d", chat_id)
    except Exception as e:
        logger.warning("tg_chat_parser: failed to respond in chat %d: %s", chat_id, e)


async def start_monitoring() -> None:
    """
    Start monitoring Telegram chats for order-related keywords.

    Uses pyrogram userbot to listen for messages in configured chats.
    Gracefully disabled if pyrogram not available or not configured.
    """
    if not is_configured():
        logger.info("tg_chat_parser: disabled (not configured)")
        return

    client_instance = _get_pyrogram_client()
    if client_instance is None:
        logger.info("tg_chat_parser: disabled (no pyrogram client)")
        return

    monitor_chats = _get_monitor_chats()
    logger.info("tg_chat_parser: starting monitoring for %d chats", len(monitor_chats))

    try:
        await client_instance.start()

        @client_instance.on_message(filters.chat(monitor_chats) & filters.text)
        async def handle_message(client_obj, message):
            await _process_message(client_obj, message)

        # Keep running
        logger.info("tg_chat_parser: monitoring active")
        while True:
            await asyncio.sleep(60)

    except Exception as e:
        logger.error("tg_chat_parser: monitoring error: %s", e)
    finally:
        try:
            if client_instance.is_connected:
                await client_instance.stop()
        except Exception:
            pass
