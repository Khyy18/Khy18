"""
Уведомления пользователям через Telegram Bot API.
Используем httpx для прямых запросов к Bot API (проще чем aiogram для разовых отправок).
Graceful degradation: если BOT_TOKEN не задан, логируем предупреждение и выходим.
"""

import logging
from decimal import Decimal

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


async def _send_message(telegram_id: int, text: str) -> bool:
    """
    Отправка сообщения пользователю через Telegram Bot API.
    Возвращает True при успехе, False при ошибке.
    """
    if not settings.BOT_TOKEN:
        logger.warning("BOT_TOKEN not set, skipping notification send")
        return False

    url = f"{TELEGRAM_API_BASE.format(token=settings.BOT_TOKEN)}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                return True
            else:
                logger.error(
                    f"Telegram API error: {response.status_code} - {response.text}"
                )
                return False
    except Exception as e:
        logger.error(f"Failed to send notification to {telegram_id}: {e}")
        return False


async def send_session_summary(telegram_id: int, summary: str) -> bool:
    """Отправка саммари сессии пользователю после завершения консультации."""
    text = (
        "<b>Итоги сессии</b>\n\n"
        f"{summary}\n\n"
        "Спасибо за сессию! Для записи на следующую откройте приложение."
    )
    return await _send_message(telegram_id, text)


async def send_low_balance_alert(telegram_id: int, balance: Decimal) -> bool:
    """Предупреждение о низком балансе."""
    text = (
        f"Внимание! Ваш баланс: {balance} руб.\n"
        "Этого может не хватить для полноценной сессии.\n\n"
        "Пополните баланс в приложении, чтобы продолжить консультации."
    )
    return await _send_message(telegram_id, text)


async def send_reminder(telegram_id: int) -> bool:
    """
    Напоминание пользователю, если он неактивен 3+ дня.
    Отправляется по расписанию из фоновой задачи.
    """
    text = (
        "Давно не виделись! \n\n"
        "Регулярные сессии помогают лучше понимать себя "
        "и справляться с трудностями.\n\n"
        "Запишитесь на консультацию в приложении."
    )
    return await _send_message(telegram_id, text)
