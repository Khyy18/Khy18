"""Планировщик автоматических откликов на фриланс-площадках."""

import asyncio
import json
import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

import config
from freelance_automation.base import FreelancePlatform, Order
from freelance_automation.config import (
    DEDUP_PATH,
    MAX_RESPONSES_PER_HOUR,
    ORDER_LIFECYCLE_PATH,
    RESPONSE_TEMPLATES,
    SCAN_INTERVAL_MINUTES,
    load_dynamic_settings,
)
from freelance_automation.telegram_admin import append_admin_error
from logging_config import get_logger

log = get_logger(__name__)


class FreelanceScheduler:
    """Планировщик сканирования и откликов на заказы."""

    def __init__(
        self,
        platforms: list[FreelancePlatform],
        keywords: list[str],
        categories: list[str] | None = None,
    ) -> None:
        self.platforms = platforms
        self._base_keywords = list(keywords)
        self._base_categories = list(categories or [])
        self._refresh_filters()
        self._responses_this_hour: list[datetime] = []
        self._responded_order_ids: set[str] = self._load_dedup()
        self._order_lifecycle: dict[str, dict[str, Any]] = self._load_lifecycle()

    def _refresh_filters(self) -> None:
        dynamic = load_dynamic_settings()
        extra_keywords = [str(k).strip() for k in dynamic.get("keywords", []) if k]
        extra_categories = [str(c).strip() for c in dynamic.get("categories", []) if c]
        self.keywords = list(dict.fromkeys(self._base_keywords + extra_keywords))
        self.categories = list(dict.fromkeys(self._base_categories + extra_categories))

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

    def _load_lifecycle(self) -> dict[str, dict[str, Any]]:
        """Load persistent lifecycle information for orders."""
        try:
            with open(ORDER_LIFECYCLE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_dedup(self) -> None:
        """Persist responded order IDs to disk."""
        try:
            with open(DEDUP_PATH, "w", encoding="utf-8") as f:
                json.dump(list(self._responded_order_ids), f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.warning("dedup_save_failed", error=str(e))

    def _save_lifecycle(self) -> None:
        """Save persistent lifecycle information for orders."""
        try:
            with open(ORDER_LIFECYCLE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._order_lifecycle, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.warning("lifecycle_save_failed", error=str(e))

    def _record_order_status(
        self,
        order: Order,
        status: str,
        platform_name: str,
    ) -> None:
        """Записать статус заказа в lifecycle storage."""
        self._order_lifecycle[order.id] = {
            "status": status,
            "title": order.title,
            "category": order.category,
            "url": order.url,
            "platform": platform_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_lifecycle()

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

    def _category_matches(self, order: Order) -> bool:
        """Проверить, подходит ли заказ по выбранным категориям."""
        if not self.categories:
            return True
        if order.category:
            return any(
                category.lower() in (order.category or "").lower()
                for category in self.categories
            )
        order_text = f"{order.title} {order.description}".lower()
        return any(category.lower() in order_text for category in self.categories)

    def _is_relevant(self, order: Order) -> bool:
        """Сравнить заказ с фильтрами по ключевым словам и категориям."""
        if not self._category_matches(order):
            return False
        if not self.keywords:
            return True
        order_text = f"{order.title} {order.description}".lower()
        return any(keyword.lower() in order_text for keyword in self.keywords)

    async def run_once(self, session: Optional[Any] = None) -> None:
        """Один цикл сканирования всех платформ и отправки откликов."""
        self._refresh_filters()
        log.info("filters_applied", keywords=self.keywords, categories=self.categories)
        owns_session = session is None
        if owns_session:
            import aiohttp

            async with aiohttp.ClientSession() as managed_session:
                await self._scan_platforms(managed_session)
        else:
            await self._scan_platforms(session)

    async def _scan_platforms(self, session: Any) -> None:
        """Scan all platforms and send responses."""
        fetch_tasks = [
            platform.fetch_new_orders(
                keywords=self.keywords if self.keywords else None,
                categories=self.categories if self.categories else None,
            )
            for platform in self.platforms
        ]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for platform, result in zip(self.platforms, fetch_results):
            platform_name = platform.__class__.__name__
            if isinstance(result, Exception):
                message = str(result)
                log.error(
                    "platform_fetch_error",
                    platform=platform_name,
                    error=message,
                )
                append_admin_error(
                    source="platform_fetch",
                    message=f"Ошибка загрузки заказов для {platform_name}",
                    details=message,
                )
                continue

            orders = result
            log.info("orders_received", platform=platform_name, count=len(orders))

            for order in orders:
                if order.id in self._responded_order_ids:
                    log.debug("order_skipped_duplicate", order_title=order.title)
                    continue

                if not self._is_relevant(order):
                    self._record_order_status(order, "ignored", platform_name)
                    log.debug(
                        "order_skipped_filter",
                        order_title=order.title,
                        category=order.category,
                    )
                    continue

                if config.FRAUD_FILTER_ENABLED:
                    from fraud_detector.integration import filter_before_response

                    is_safe = await filter_before_response(session, order)
                    if not is_safe:
                        log.info("order_skipped_fraud", order_title=order.title)
                        self._record_order_status(order, "fraud_skipped", platform_name)
                        continue

                if not self._can_respond():
                    log.warning(
                        "rate_limit_reached",
                        limit=MAX_RESPONSES_PER_HOUR,
                    )
                    return

                text = self._pick_template(order)
                success = await platform.respond_to_order(order, text, use_ai=True)

                if success:
                    self._responses_this_hour.append(datetime.now(timezone.utc))
                    self._responded_order_ids.add(order.id)
                    self._save_dedup()
                    self._record_order_status(order, "responded", platform_name)
                    log.info("response_sent", order_title=order.title)
                else:
                    self._record_order_status(order, "response_failed", platform_name)
                    log.warning("response_failed", order_title=order.title)
                    append_admin_error(
                        source="response_failed",
                        message=f"Не удалось отправить отклик на заказ {order.id}",
                        details=order.title,
                    )

    async def run_loop(self) -> None:
        """Бесконечный цикл сканирования с заданным интервалом."""
        log.info(
            "scheduler_started",
            interval_minutes=SCAN_INTERVAL_MINUTES,
        )
        try:
            while True:
                await self.run_once()
                await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            log.info("scheduler_cancelled")
            raise
        finally:
            await self.close()

    async def run_forever(self) -> None:
        """Alias для backward compatibility."""
        await self.run_loop()

    async def close(self) -> None:
        """Закрыть браузеры всех подключённых платформ."""
        for platform in self.platforms:
            try:
                await platform.close()
            except Exception as e:
                log.warning("platform_close_failed", platform=platform.__class__.__name__, error=str(e))
