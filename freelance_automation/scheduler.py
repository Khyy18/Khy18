"""Планировщик автоматических откликов на фриланс-площадках."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

from freelance_automation.base import FreelancePlatform, Order
from freelance_automation.config import (
    MAX_RESPONSES_PER_HOUR,
    RESPONSE_TEMPLATES,
    SCAN_INTERVAL_MINUTES,
)

logger = logging.getLogger(__name__)


class FreelanceScheduler:
    """Планировщик сканирования и откликов на заказы."""

    def __init__(self, platforms: list[FreelancePlatform], keywords: list[str]) -> None:
        self.platforms = platforms
        self.keywords = keywords
        self._responses_this_hour: list[datetime] = []

    def _cleanup_old_responses(self) -> None:
        """Удаление записей старше 1 часа из счётчика откликов."""
        now = datetime.now(timezone.utc)
        self._responses_this_hour = [
            t for t in self._responses_this_hour
            if (now - t).total_seconds() < 3600
        ]

    def _can_respond(self) -> bool:
        """Проверка лимита откликов в час."""
        self._cleanup_old_responses()
        return len(self._responses_this_hour) < MAX_RESPONSES_PER_HOUR

    def _pick_template(self, order: Order) -> str:
        """Выбор случайного шаблона и подстановка данных заказа."""
        template = random.choice(RESPONSE_TEMPLATES)
        budget_str = str(int(order.budget)) if order.budget else "договорный"
        return template.format(title=order.title, budget=budget_str)

    async def run_once(self) -> None:
        """Один цикл сканирования всех платформ и отправки откликов."""
        for platform in self.platforms:
            try:
                orders = await platform.fetch_new_orders(
                    keywords=self.keywords if self.keywords else None
                )
                logger.info(f"Получено {len(orders)} заказов с платформы")

                for order in orders:
                    if not self._can_respond():
                        logger.warning(
                            f"Достигнут лимит откликов: {MAX_RESPONSES_PER_HOUR}/час"
                        )
                        break

                    text = self._pick_template(order)
                    success = await platform.respond_to_order(order, text)

                    if success:
                        self._responses_this_hour.append(datetime.now(timezone.utc))
                        logger.info(f"Отклик отправлен: {order.title}")
                    else:
                        logger.warning(f"Не удалось отправить отклик: {order.title}")

            except Exception as e:
                logger.error(f"Ошибка при обработке платформы: {e}")

    async def run_loop(self) -> None:
        """Бесконечный цикл сканирования с заданным интервалом."""
        logger.info(
            f"Запуск планировщика фриланса (интервал: {SCAN_INTERVAL_MINUTES} мин)"
        )
        while True:
            await self.run_once()
            await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)
