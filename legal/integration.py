"""Оркестратор: вызывается из payments при первом платеже."""

import aiohttp

from .generator import OfferGenerator
from .models import is_first_payment, mark_accepted
from .sender import send_offer_to_telegram


async def on_first_payment(session: aiohttp.ClientSession, user_tg_id: int,
                           user_name: str, amount: float,
                           description: str):
    """Вызывается из модуля payments при successful_payment.

    Если это первый платеж пользователя - генерирует PDF оферту,
    отправляет в Telegram и отмечает акцепт (оплата = принятие).
    """
    if not is_first_payment(user_tg_id):
        return None  # не первый платеж, пропускаем

    generator = OfferGenerator()
    pdf_bytes, offer_id = generator.generate_pdf(
        user_tg_id, user_name, amount, description
    )
    filename = f"offer_{offer_id}.pdf"
    await send_offer_to_telegram(session, user_tg_id, pdf_bytes, filename)
    mark_accepted(offer_id)  # оплата = акцепт
    return offer_id
