"""Сервис автоматического ведения Telegram-канала."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ChannelAutopilot:
    """
    Автопилот для Telegram-канала.
    Бот ведёт канал как 'автор': публикует подборки, анонсы, опросы.
    """

    CONTENT_TYPES = [
        "daily_top",        # Топ-5 скидок дня
        "flash_deal",       # Молниеносная скидка (>40%)
        "price_drop_alert", # Товар упал до исторического минимума
        "weekly_review",    # Еженедельный обзор
        "poll",             # Опрос подписчиков
        "tip",              # Полезный совет по экономии
    ]

    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.channel_id = settings.telegram_channel_id

    async def post_to_channel(self, text: str, parse_mode: str = "HTML") -> bool:
        """Опубликовать сообщение в канал."""
        if not self.bot_token or not self.channel_id:
            logger.warning("Channel autopilot not configured")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": self.channel_id,
                    "text": text,
                    "parse_mode": parse_mode,
                })
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            return False

    def format_daily_top(self, products: list[dict]) -> str:
        """Форматировать пост 'Топ-5 скидок дня'."""
        lines = ["\U0001f525 <b>Топ-5 скидок дня</b>", "\u2501" * 24, ""]
        for i, p in enumerate(products[:5], 1):
            old = f"{p['old_price']:,.0f}".replace(",", "\u202f")
            new = f"{p['new_price']:,.0f}".replace(",", "\u202f")
            lines.append(f"{i}. <b>{p['name'][:40]}</b>")
            lines.append(f"   <s>{old} \u20bd</s> \u2192 <b>{new} \u20bd</b> (\u2212{p['discount']}%)")
            lines.append(f"   <a href=\"{p['url']}\">Купить \u2192</a>")
            lines.append("")
        lines.append("\u2501" * 24)
        lines.append("\U0001f4f1 Больше скидок в боте: @PriceMonitorBot")
        return "\n".join(lines)

    def format_flash_deal(self, product: dict) -> str:
        """Форматировать пост 'Молниеносная скидка'."""
        old = f"{product['old_price']:,.0f}".replace(",", "\u202f")
        new = f"{product['new_price']:,.0f}".replace(",", "\u202f")
        savings = f"{product['old_price'] - product['new_price']:,.0f}".replace(",", "\u202f")
        return (
            f"\u26a1 <b>FLASH DEAL \u2212{product['discount']}%</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"<b>{product['name']}</b>\n\n"
            f"<s>{old} \u20bd</s> \u2192 <b>{new} \u20bd</b>\n\n"
            f"\U0001f4b0 Экономия: {savings} \u20bd\n\n"
            f"<a href=\"{product['url']}\">\U0001f6d2 Купить со скидкой \u2192</a>\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\u23f0 Цена может вернуться в любой момент"
        )

    def format_weekly_review(self, stats: dict) -> str:
        """Форматировать еженедельный обзор."""
        total_savings = f"{stats.get('total_savings', 0):,.0f}".replace(",", "\u202f")
        return (
            f"\U0001f4ca <b>Итоги недели</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"\U0001f3f7 Найдено скидок: {stats.get('total_deals', 0)}\n"
            f"\U0001f4c9 Средняя скидка: {stats.get('avg_discount', 0)}%\n"
            f"\U0001f3c6 Максимальная: {stats.get('max_discount', 0)}%\n"
            f"\U0001f4b0 Экономия подписчиков: {total_savings} \u20bd\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Подключай бот и экономь: @PriceMonitorBot"
        )

    def format_poll(self, question: str, options: list[str]) -> dict:
        """Подготовить опрос для канала."""
        return {
            "chat_id": self.channel_id,
            "question": question,
            "options": options,
            "is_anonymous": True,
        }

    async def post_poll(self, question: str, options: list[str]) -> bool:
        """Опубликовать опрос в канал."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPoll"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=self.format_poll(question, options))
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to post poll: {e}")
            return False


channel_autopilot = ChannelAutopilot()
