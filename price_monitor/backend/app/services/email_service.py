"""Сервис email-рассылок."""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    html_body: str


class EmailService:
    """Отправка email через SMTP или API (Resend/Mailgun)."""

    def __init__(self):
        self.api_key = settings.email_api_key
        self.from_email = settings.email_from
        self.base_url = settings.email_api_url

    async def send(self, message: EmailMessage) -> bool:
        """Отправить email через API."""
        if not self.api_key:
            logger.warning("Email API key not configured, skipping send")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.base_url}/emails",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "from": self.from_email,
                        "to": [message.to],
                        "subject": message.subject,
                        "html": message.html_body,
                    },
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send email to {message.to}: {e}")
            return False

    async def send_digest(self, to: str, products: list[dict]) -> bool:
        """Отправить дайджест скидок."""
        items_html = ""
        for p in products[:5]:
            items_html += f"""
            <tr>
                <td style="padding:8px">{p['name']}</td>
                <td style="padding:8px;text-decoration:line-through;color:#999">{p['old_price']} ₽</td>
                <td style="padding:8px;color:#FF6B35;font-weight:bold">{p['new_price']} ₽</td>
                <td style="padding:8px;color:green">-{p['discount']}%</td>
            </tr>
            """

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
            <h2 style="color:#FF6B35">🔥 Ваш дайджест скидок</h2>
            <p>Топ-5 лучших предложений за сегодня:</p>
            <table style="width:100%;border-collapse:collapse">
                <tr style="background:#f5f5f5">
                    <th style="padding:8px;text-align:left">Товар</th>
                    <th style="padding:8px">Было</th>
                    <th style="padding:8px">Стало</th>
                    <th style="padding:8px">Скидка</th>
                </tr>
                {items_html}
            </table>
            <p style="margin-top:20px">
                <a href="https://t.me/PriceMonitorBot" style="background:#FF6B35;color:white;padding:10px 20px;text-decoration:none;border-radius:6px">
                    Открыть бот
                </a>
            </p>
            <p style="color:#999;font-size:12px;margin-top:30px">
                Вы получили это письмо, потому что подписаны на дайджест Price Monitor.
                <a href="{{{{unsubscribe_url}}}}">Отписаться</a>
            </p>
        </div>
        """

        return await self.send(EmailMessage(
            to=to,
            subject="🔥 Топ-5 скидок для вас — Price Monitor",
            html_body=html,
        ))


email_service = EmailService()
