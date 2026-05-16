"""Lifecycle-сообщения: автоматическая отправка в Telegram при смене этапа."""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from logging_config import get_logger

log = get_logger(__name__)

# Шаблоны сообщений для переходов.
LIFECYCLE_MESSAGES: dict[tuple[str, str], str] = {
    ("lead", "trial"): (
        "Добро пожаловать в пробный период! "
        "У вас есть 7 дней, чтобы оценить все возможности."
    ),
    ("trial", "paid"): (
        "Спасибо за оплату! Рады, что вы с нами. "
        "Все премиум-функции активированы."
    ),
    ("paid", "churned"): (
        "Мы скучаем по вам! Вернитесь и получите скидку 20% "
        "на следующий месяц. Промокод: COMEBACK20"
    ),
}


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("lifecycle_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("lifecycle_send_error", error=str(e), chat_id=chat_id)
        return None


async def send_lifecycle_message(
    session: aiohttp.ClientSession,
    tg_id: int,
    old_stage: str,
    new_stage: str,
) -> None:
    """Отправить lifecycle-сообщение клиенту при смене этапа."""
    message = LIFECYCLE_MESSAGES.get((old_stage, new_stage))
    if message is None:
        log.debug("no_lifecycle_message", old_stage=old_stage, new_stage=new_stage)
        return

    log.info("sending_lifecycle_message", tg_id=tg_id, transition=f"{old_stage}->{new_stage}")
    await _send_message(session, tg_id, message)
