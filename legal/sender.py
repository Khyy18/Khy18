"""Отправка PDF оферты через Telegram Bot API."""

from io import BytesIO

import aiohttp

import config


async def send_offer_to_telegram(session: aiohttp.ClientSession, chat_id: int,
                                 pdf_bytes: bytes, filename: str) -> bool:
    """Отправка PDF документа в Telegram чат через sendDocument (multipart)."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendDocument"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    data.add_field("document", BytesIO(pdf_bytes), filename=filename,
                   content_type="application/pdf")
    data.add_field("caption", "\U0001f4c4 Ваш договор-оферта. Оплата = акцепт условий.")

    try:
        async with session.post(url, data=data) as resp:
            return resp.status == 200
    except aiohttp.ClientError:
        return False
