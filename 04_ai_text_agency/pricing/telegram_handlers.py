"""Telegram-обработчики для Pricing.

Команды: /price, /pricing_stats
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from logging_config import get_logger
from pricing.service import get_price

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


async def handle_price_command(
    session: aiohttp.ClientSession,
    chat_id: int,
    service_type: str,
    base_price: float,
) -> None:
    """Обработчик /price - показать рассчитанную цену."""
    price = get_price(base_price, service_type, client_tg_id=chat_id)

    text = (
        f"<b>Расчет цены:</b>\n\n"
        f"Услуга: {service_type}\n"
        f"Базовая цена: {base_price:.2f}\n"
        f"Итоговая цена: <b>{price:.2f}</b>"
    )
    await _send_message(session, chat_id, text)
    log.info("price_command", chat_id=chat_id, service_type=service_type, price=price)


async def handle_pricing_stats_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Обработчик /pricing_stats - показать статистику ценообразования."""
    text = (
        "<b>Статистика ценообразования:</b>\n\n"
        f"Базовый мультипликатор: {config.PRICING_BASE_MULTIPLIER}\n"
        f"Пиковые часы: 10:00-18:00 UTC\n"
        f"Надбавка за нагрузку: +20% (при >5 заказах)\n"
        f"Скидка повторного клиента: -10%\n"
        f"Надбавка за премиум-сервис: +30%"
    )
    await _send_message(session, chat_id, text)
    log.info("pricing_stats_command", chat_id=chat_id)
