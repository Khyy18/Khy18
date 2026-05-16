"""Реализация платформы FL.ru через Playwright."""

from __future__ import annotations

import json
from typing import Optional

from playwright.async_api import Browser, Page, async_playwright

from freelance_automation.base import FreelancePlatform, Order
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
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._playwright = None
        self.stealth_config = stealth_config

    async def login(self, cookies_path: str) -> bool:
        """Авторизация на FL.ru через загрузку cookies из JSON файла."""
        try:
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

    async def fetch_new_orders(self, keywords: list[str] | None = None) -> list[Order]:
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

                order = Order(
                    id=order_id,
                    title=title,
                    description=description,
                    budget=budget,
                    url=url,
                )

                # Фильтрация по ключевым словам
                if keywords:
                    text_lower = f"{title} {description}".lower()
                    if not any(kw.lower() in text_lower for kw in keywords):
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
            await textarea.fill(response_text)

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
