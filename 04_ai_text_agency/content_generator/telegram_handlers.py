"""Telegram-обработчики для Content Generator.

Команды: /content, /generate_case
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from content_generator.generator import ContentGenerator
from logging_config import get_logger

log = get_logger(__name__)

_generator = ContentGenerator()


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("telegram_send_error", error=str(e), chat_id=chat_id)
        return None


async def handle_content_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Обработчик /content - показать информацию о генераторе контента."""
    text = (
        "<b>Генератор контента</b>\n\n"
        "Доступные команды:\n"
        "/generate_case [order_id] - сгенерировать кейс\n"
        "/content - эта справка\n\n"
        "Автогенерация постов: ежедневно в "
        f"{config.CONTENT_GENERATION_HOUR}:00 UTC"
    )
    await _send_message(session, chat_id, text)
    log.info("content_command", chat_id=chat_id)


async def handle_generate_case_command(
    session: aiohttp.ClientSession,
    chat_id: int,
    order_id: str,
) -> None:
    """Обработчик /generate_case - сгенерировать кейс для заказа."""
    completed_order = {
        "title": f"Order {order_id}",
        "description": f"Completed project for order {order_id}",
        "result": "Successfully delivered",
    }

    await _send_message(session, chat_id, "Генерирую кейс...")

    case_text = await _generator.generate_case_study(session, completed_order)

    if case_text:
        await _send_message(session, chat_id, f"<b>Кейс:</b>\n\n{case_text}")
    else:
        await _send_message(session, chat_id, "Не удалось сгенерировать кейс.")

    log.info("generate_case_command", chat_id=chat_id, order_id=order_id)
