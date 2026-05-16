"""Отправка персональных алертов пользователям о снижении цен."""

import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.db.queries import get_active_alerts_for_keyword, get_user
from bot.publisher.affiliate import build_affiliate_link
from bot.ui.cards import card, format_number

logger = logging.getLogger(__name__)


class AlertSender:
    """Отправка персональных уведомлений о снижении цен."""

    def __init__(self, bot: Bot, scheduler: AsyncIOScheduler, db_path: str | None = None) -> None:
        self._bot = bot
        self._scheduler = scheduler
        self._db_path = db_path or settings.db_path

    async def check_and_send_alerts(
        self, product: dict[str, Any], new_price: float
    ) -> None:
        """Проверить алерты и отправить уведомления пользователям.

        Логика: получаем все активные алерты, проверяем совпадение
        keyword (целое слово, регистронезависимо) в названии товара.

        Args:
            product: dict с информацией о товаре (name, marketplace, article_id/product_id, url).
            new_price: новая (текущая) цена товара.
        """
        product_name = product.get("name", "")
        if not product_name:
            return

        product_name_lower = product_name.lower()

        # Получаем все активные алерты
        all_alerts = await get_active_alerts_for_keyword("")
        matched_alerts: list[dict[str, Any]] = []

        for alert in all_alerts:
            keyword = alert.get("keyword", "").lower()
            if not keyword:
                continue

            # Проверяем, что ключевое слово содержится в названии товара
            if keyword not in product_name_lower:
                continue

            # Проверяем порог цены
            max_price = alert.get("max_price")
            if max_price is not None and new_price > max_price:
                continue

            matched_alerts.append(alert)

        if not matched_alerts:
            return

        # Формируем сообщение
        message = self._format_alert(product, new_price)

        # Отправляем каждому пользователю
        for alert in matched_alerts:
            user_id = alert.get("user_id")
            if not user_id:
                continue

            user = await get_user(user_id)
            if not user:
                continue

            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            is_vip = user.get("is_vip", False)

            if is_vip:
                # VIP - отправляем сразу
                await self._send_alert(telegram_id, message)
            else:
                # Бесплатные пользователи - с задержкой через APScheduler (date trigger)
                delay = settings.free_delay_seconds
                run_date = datetime.now() + timedelta(seconds=delay)
                self._scheduler.add_job(
                    self._send_alert,
                    trigger="date",
                    run_date=run_date,
                    args=[telegram_id, message],
                )

    async def _send_alert(self, telegram_id: int, message: str) -> None:
        """Отправить алерт пользователю."""
        try:
            await self._bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode="HTML",
            )
            logger.info("Алерт отправлен пользователю %d", telegram_id)
        except Exception as e:
            logger.error("Ошибка отправки алерта пользователю %d: %s", telegram_id, e)

    def _format_alert(self, product: dict[str, Any], new_price: float) -> str:
        """Форматирование сообщения об алерте."""
        name = product.get("name", "Товар")
        old_price = product.get("old_price", 0)
        marketplace = product.get("marketplace", "")
        product_url = product.get("url", "")

        # Партнерская ссылка
        affiliate_link = ""
        if product_url and marketplace:
            affiliate_link = build_affiliate_link(
                product_url, marketplace, settings.affiliate_tag
            )

        body_lines = [
            f"\U0001f4b0 Цена: <s>{format_number(old_price)} \u20bd</s> \u2192 <b>{format_number(new_price)} \u20bd</b>",
        ]

        if old_price > 0:
            drop_percent = round((1 - new_price / old_price) * 100)
            body_lines.append(f"\U0001f4c9 Снижение: {drop_percent}%")

        if affiliate_link:
            body_lines.append(f'\n<a href="{affiliate_link}">Перейти к товару</a>')

        return card(name, "\U0001f514", body_lines)
