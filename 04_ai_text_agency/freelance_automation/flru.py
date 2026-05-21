"""Реализация платформы FL.ru через Playwright."""

from __future__ import annotations

import json
import os
import random
from typing import Any, Optional

from freelance_automation.base import FreelancePlatform, Order
from freelance_automation.config import DELIVERABLES_PATH
from freelance_automation.stealth import (
    StealthConfig,
    apply_stealth,
    get_random_user_agent,
    get_random_viewport,
    random_delay,
)
from logging_config import get_logger

log = get_logger(__name__)


class FLruPlatform(FreelancePlatform):
    """Автоматизация площадки FL.ru."""

    BASE_URL = "https://www.fl.ru"
    PROJECTS_URL = "https://www.fl.ru/projects/"

    def __init__(self, stealth_config: Optional[StealthConfig] = None) -> None:
        self._browser: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self.stealth_config = stealth_config

    async def login(self, cookies_path: str) -> bool:
        """Авторизация на FL.ru через загрузку cookies из JSON файла."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Параметры запуска браузера
            launch_kwargs: dict = {"headless": True}
            context_kwargs: dict = {}

            if self.stealth_config:
                # Прокси
                if self.stealth_config.proxy:
                    launch_kwargs["proxy"] = {"server": self.stealth_config.proxy}
                # User-Agent и viewport
                ua = get_random_user_agent(self.stealth_config)
                viewport = get_random_viewport()
                context_kwargs["user_agent"] = ua
                context_kwargs["viewport"] = viewport

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            context = await self._browser.new_context(**context_kwargs)

            # Загрузка cookies из файла
            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)

            self._page = await context.new_page()

            # Применение playwright-stealth
            if self.stealth_config and self.stealth_config.enable_stealth:
                await apply_stealth(self._page)

            await self._page.goto(self.BASE_URL)

            log.info("auth_success", platform="fl.ru")
            return True
        except Exception as e:
            log.error("auth_failed", platform="fl.ru", error=str(e))
            return False

    async def _delay(self) -> None:
        """Задержка между действиями для имитации поведения человека."""
        if self.stealth_config:
            await random_delay(
                self.stealth_config.min_delay, self.stealth_config.max_delay
            )

    async def _human_type_text(self, textarea, text: str) -> None:
        """Ввод текста по-людски, чтобы снизить риск блокировки."""
        await textarea.click()
        await self._delay()
        await textarea.fill("")
        if len(text) <= 300:
            await textarea.type(text, delay=random.randint(40, 80))
        else:
            for chunk in [text[i : i + 200] for i in range(0, len(text), 200)]:
                await textarea.type(chunk, delay=random.randint(30, 70))
                await self._delay()

    async def _extract_category_from_card(self, card) -> Optional[str]:
        """Попытаться извлечь категорию заказа из карточки FL.ru."""
        selectors = [
            ".b-post__category",
            ".b-post__tags",
            ".b-post__info .category",
            ".b-post__title .tag",
        ]
        for selector in selectors:
            el = await card.query_selector(selector)
            if el:
                text = (await el.inner_text() or "").strip()
                if text:
                    return text
        return None

    async def _infer_category(self, title: str, description: str) -> Optional[str]:
        """Инферировать категорию из текста заказа, если она не указана явно."""
        text = f"{title} {description}".lower()
        category_keywords = {
            "telegram": ["telegram", "бот", "бота", "ботов"],
            "парсинг": ["парс", "scrapy", "парсер"],
            "веб": ["django", "flask", "веб", "frontend", "backend", "api"],
            "мобильное": ["flutter", "ios", "android", "мобильн"],
            "маркетинг": ["реклама", "marketing", "seo"],
        }
        for category, keywords in category_keywords.items():
            if any(keyword in text for keyword in keywords):
                return category
        return None

    async def _scroll_page(self) -> None:
        """Небольшая прокрутка страницы для имитации просмотра."""
        if not self._page:
            return
        try:
            await self._page.mouse.wheel(0, random.randint(200, 500))
            await self._delay()
            await self._page.mouse.wheel(0, random.randint(-150, 150))
            await self._delay()
        except Exception:
            pass

    async def fetch_new_orders(
        self,
        keywords: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> list[Order]:
        """Получение новых заказов со страницы проектов FL.ru."""
        if not self._page:
            log.error("browser_not_initialized", platform="fl.ru")
            return []

        try:
            await self._page.goto(self.PROJECTS_URL)
            await self._delay()
            await self._page.wait_for_selector("#projects-list", timeout=10000)

            cards = await self._page.query_selector_all("#projects-list .b-post")
            orders: list[Order] = []

            for card in cards:
                title_el = await card.query_selector(".b-post__title a")
                desc_el = await card.query_selector(".b-post__body")
                price_el = await card.query_selector(".b-post__price .count")

                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                href = await title_el.get_attribute("href") or ""
                description = ""
                if desc_el:
                    description = (await desc_el.inner_text()).strip()

                budget = None
                if price_el:
                    price_text = (await price_el.inner_text()).strip()
                    price_text = price_text.replace(" ", "").replace("\xa0", "")
                    try:
                        budget = float(price_text)
                    except ValueError:
                        pass

                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                order_id = href.split("/")[-1] if href else title[:20]
                category = await self._extract_category_from_card(card)
                if not category:
                    category = await self._infer_category(title, description)

                order = Order(
                    id=order_id,
                    title=title,
                    description=description,
                    budget=budget,
                    url=url,
                    category=category,
                )

                if keywords:
                    text_lower = f"{title} {description}".lower()
                    if not any(kw.lower() in text_lower for kw in keywords):
                        continue

                if categories:
                    category_lower = (category or "").lower()
                    if not any(cat.lower() in category_lower for cat in categories):
                        text_lower = f"{title} {description}".lower()
                        if not any(cat.lower() in text_lower for cat in categories):
                            continue

                orders.append(order)

            log.info("orders_fetched", platform="fl.ru", count=len(orders))
            return orders
        except Exception as e:
            log.error("fetch_orders_failed", platform="fl.ru", error=str(e))
            return []

    async def respond_to_order(
        self, order: Order, text: str, use_ai: bool = True
    ) -> bool:
        """Отправка отклика на заказ FL.ru.

        Args:
            order: Заказ для отклика.
            text: Текст отклика (используется если use_ai=False или AI недоступен).
            use_ai: Генерировать отклик через AI вместо переданного текста.
        """
        if not self._page:
            log.error("browser_not_initialized", platform="fl.ru")
            return False

        response_text = text
        if use_ai:
            try:
                import aiohttp

                from freelance_automation.ai_responder import AIResponder
                from freelance_automation.portfolio import select_relevant

                portfolio_items = select_relevant(order)
                responder = AIResponder()
                async with aiohttp.ClientSession() as session:
                    ai_text = await responder.generate_response(
                        session, order, "fl.ru", portfolio_items
                    )
                    if ai_text:
                        response_text = ai_text
            except Exception as e:
                log.warning("ai_responder_unavailable", error=str(e))

        try:
            await self._page.goto(order.url)
            await self._delay()
            await self._page.wait_for_selector(".b-post__form", timeout=10000)

            # Заполнение формы отклика
            textarea = await self._page.query_selector(".b-post__form textarea")
            if not textarea:
                log.error("response_form_not_found", order_id=order.id)
                return False

            await self._delay()
            await self._scroll_page()
            await self._delay()
            await self._human_type_text(textarea, response_text)

            # Отправка формы
            submit_btn = await self._page.query_selector(".b-post__form button[type='submit']")
            if submit_btn:
                await self._delay()
                await submit_btn.click()
                await self._page.wait_for_timeout(2000)

            log.info("response_sent", platform="fl.ru", order_title=order.title)
            return True
        except Exception as e:
            log.error("response_failed", platform="fl.ru", error=str(e))
            return False

    async def check_order_status(self, order: Order) -> str:
        """Проверка статуса заказа на FL.ru."""
        if not self._page:
            log.error("browser_not_initialized", platform="fl.ru")
            return "pending"

        try:
            await self._page.goto(order.url)
            await self._delay()
            await self._page.wait_for_timeout(3000)

            page_text = (await self._page.content()).lower()
            if "заказ принят" in page_text or "заказ одобрен" in page_text or "выбран" in page_text:
                return "accepted"
            if "отклонен" in page_text or "отменен" in page_text or "не выбран" in page_text:
                return "rejected"

            accept_btn = await self._page.query_selector("button:has-text('Принять заказ'), button:has-text('Принять')")
            if accept_btn:
                await self._delay()
                await accept_btn.click()
                await self._page.wait_for_timeout(2000)
                return "accepted"

            return "pending"
        except Exception as e:
            log.error("check_order_status_failed", platform="fl.ru", error=str(e))
            return "pending"

    async def _attach_deliverable_file(self, file_path: str) -> bool:
        if not self._page:
            return False

        try:
            file_input = await self._page.query_selector("input[type=file]")
            if not file_input:
                attach_button = await self._page.query_selector(
                    "button:has-text('Прикрепить'), button:has-text('Добавить файл'), button:has-text('Attach file')"
                )
                if attach_button:
                    await self._delay()
                    await attach_button.click()
                    await self._delay()
                    file_input = await self._page.query_selector("input[type=file]")

            if file_input and os.path.exists(file_path):
                await file_input.set_input_files(file_path)
                await self._delay()
                return True
        except Exception as e:
            log.warning("file_attachment_failed", platform="fl.ru", error=str(e))
        return False

    async def deliver_order(self, order: Order, completion_text: str) -> bool:
        """Отправка готового результата клиенту на FL.ru."""
        if not self._page:
            log.error("browser_not_initialized", platform="fl.ru")
            return False

        try:
            await self._page.goto(order.url)
            await self._delay()
            await self._page.wait_for_timeout(3000)

            zip_path = os.path.join(DELIVERABLES_PATH, order.id, "deliverable.zip")
            if os.path.exists(zip_path):
                attached = await self._attach_deliverable_file(zip_path)
                if not attached:
                    try:
                        from freelance_automation.telegram_admin import send_manual_file_upload_alert

                        await send_manual_file_upload_alert(order.id, zip_path, "fl.ru")
                    except Exception as exc:
                        log.warning("manual_upload_alert_failed", platform="fl.ru", error=str(exc))

            textarea = await self._page.query_selector("textarea, .chat-input textarea, .message-form textarea")
            if not textarea:
                log.warning("completion_textarea_not_found", platform="fl.ru")
                return False

            await self._human_type_text(textarea, completion_text)
            send_btn = await self._page.query_selector("button:has-text('Отправить'), button:has-text('Отправить сообщение'), button:has-text('Send')")
            if send_btn:
                await self._delay()
                await send_btn.click()
                await self._page.wait_for_timeout(2000)

            log.info("order_delivered", platform="fl.ru", order_id=order.id)
            return True
        except Exception as e:
            log.error("delivery_failed", platform="fl.ru", error=str(e))
            return False

    async def close(self) -> None:
        """Закрытие браузера."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            log.info("browser_closed", platform="fl.ru")
        except Exception as e:
            log.error("browser_close_failed", platform="fl.ru", error=str(e))
