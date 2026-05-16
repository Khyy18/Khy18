"""Планировщик автоматических откликов на фриланс-площадках."""

import asyncio
import json
import os
import random
from datetime import datetime, timezone
from typing import Optional

from freelance_automation.base import FreelancePlatform, Order
from freelance_automation.config import (
    MAX_RESPONSES_PER_HOUR,
    RESPONSE_TEMPLATES,
    SCAN_INTERVAL_MINUTES,
)
from logging_config import get_logger

log = get_logger(__name__)

# Path for persisting responded order IDs across restarts
DEDUP_PATH: str = os.getenv("FREELANCE_DEDUP_PATH", "freelance_responded.json")


class FreelanceScheduler:
    """Планировщик сканирования и откликов на заказы."""

    def __init__(self, platforms: list[FreelancePlatform], keywords: list[str]) -> None:
        self.platforms = platforms
        self.keywords = keywords
        self._responses_this_hour: list[datetime] = []
        self._responded_order_ids: set[str] = self._load_dedup()

    def _load_dedup(self) -> set[str]:
        """Load responded order IDs from persistent storage."""
        try:
            with open(DEDUP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return set()

    def _save_dedup(self) -> None:
        """Persist responded order IDs to disk."""
        try:
            with open(DEDUP_PATH, "w", encoding="utf-8") as f:
                json.dump(list(self._responded_order_ids), f)
        except OSError as e:
            log.warning("dedup_save_failed", error=str(e))

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
                log.info("orders_received", count=len(orders))

                for order in orders:
                    # Skip already-responded orders
                    if order.id in self._responded_order_ids:
                        log.debug("order_skipped_duplicate", order_title=order.title)
                        continue

                    if not self._can_respond():
                        log.warning(
                            "rate_limit_reached",
                            limit=MAX_RESPONSES_PER_HOUR,
                        )
                        break

                    text = self._pick_template(order)
                    success = await platform.respond_to_order(order, text)

                    if success:
                        self._responses_this_hour.append(datetime.now(timezone.utc))
                        self._responded_order_ids.add(order.id)
                        self._save_dedup()
                        log.info("response_sent", order_title=order.title)
                    else:
                        log.warning("response_failed", order_title=order.title)

            except Exception as e:
                log.error("platform_processing_error", error=str(e))

    async def run_loop(self) -> None:
        """Бесконечный цикл сканирования с заданным интервалом."""
        log.info(
            "scheduler_started",
            interval_minutes=SCAN_INTERVAL_MINUTES,
        )
        while True:
            await self.run_once()
            await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)
