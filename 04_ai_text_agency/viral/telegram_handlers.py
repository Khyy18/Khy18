"""Telegram-обработчики для реферальной системы.

Используют aiohttp напрямую (как telegram_bot.py) для отправки сообщений
через Telegram Bot API.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from logging_config import get_logger
from viral import models

log = get_logger(__name__)


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


def _format_stats_message(stats: dict) -> str:
    """Форматировать статистику рефералов в HTML для Telegram."""
    return (
        "<b>Ваша реферальная статистика:</b>\n"
        f"Приглашено: {stats.get('invited', 0)}\n"
        f"Оплатили: {stats.get('paid', 0)}\n"
        f"Ожидают оплаты: {stats.get('pending', 0)}\n"
        f"Бонусов получено: {stats.get('bonuses_earned', 0)}"
    )


async def handle_referral_command(
    session: aiohttp.ClientSession,
    chat_id: int,
    user_id: int,
    bot_username: str,
) -> None:
    """Обработчик команды /referral - отправляет ссылку и статистику."""
    models.init_db()
    code = models.create_referral_code(user_id)
    link = f"https://t.me/{bot_username}?start=ref_{code}"
    stats = models.get_referral_stats(user_id)

    log.info("referral_command", user_id=user_id, code=code)

    text = (
        f"<b>Ваша реферальная ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        f"Поделитесь ссылкой с друзьями. Когда приглашённый оплатит "
        f"первый заказ, вы получите бесплатный заказ!\n\n"
        f"{_format_stats_message(stats)}"
    )
    await _send_message(session, chat_id, text)


async def handle_start_referral(
    session: aiohttp.ClientSession,
    chat_id: int,
    user_id: int,
    start_param: str,
) -> None:
    """Обработчик deep link /start ref_CODE - регистрирует реферал."""
    models.init_db()

    # Парсим код из параметра start (формат: ref_XXXXXXXX)
    if not start_param.startswith("ref_"):
        return
    code = start_param[4:]
    if not code:
        return

    success = models.register_referral(code, user_id)
    if success:
        log.info("referral_registered", user_id=user_id, code=code)
        text = "Вы зарегистрированы по реферальной ссылке! Добро пожаловать."
    else:
        text = "Добро пожаловать!"
    await _send_message(session, chat_id, text)
