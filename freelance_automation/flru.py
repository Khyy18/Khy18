"""Реализация платформы FL.ru через Playwright."""

import json
import logging
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page

from freelance_automation.base import FreelancePlatform, Order

logger = logging.getLogger(__name__)


class FLruPlatform(FreelancePlatform):
    """Автоматизация площадки FL.ru."""

    BASE_URL = "https://www.fl.ru"
    PROJECTS_URL = "https://www.fl.ru/projects/"

    def __init__(self) -> None:
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._playwright = None

    async def login(self, cookies_path: str) -> bool:
        """Авторизация на FL.ru через загрузку cookies из JSON файла."""
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context()

            # Загрузка cookies из файла
            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)

            self._page = await context.new_page()
            await self._page.goto(self.BASE_URL)

            logger.info("Успешная авторизация на FL.ru")
            return True
        except Exception as e:
            logger.error(f"Ошибка авторизации на FL.ru: {e}")
            return False

    async def fetch_new_orders(self, keywords: list[str] | None = None) -> list[Order]:
        """Получение новых заказов со страницы проектов FL.ru."""
        if not self._page:
            logger.error("Браузер не инициализирован. Сначала вызовите login().")
            return []

        try:
            await self._page.goto(self.PROJECTS_URL)
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

            logger.info(f"Найдено {len(orders)} заказов на FL.ru")
            return orders
        except Exception as e:
            logger.error(f"Ошибка получения заказов с FL.ru: {e}")
            return []

    async def respond_to_order(self, order: Order, text: str) -> bool:
        """Отправка отклика на заказ FL.ru."""
        if not self._page:
            logger.error("Браузер не инициализирован.")
            return False

        try:
            await self._page.goto(order.url)
            await self._page.wait_for_selector(".b-post__form", timeout=10000)

            # Заполнение формы отклика
            textarea = await self._page.query_selector(".b-post__form textarea")
            if not textarea:
                logger.error(f"Форма отклика не найдена для заказа {order.id}")
                return False

            await textarea.fill(text)

            # Отправка формы
            submit_btn = await self._page.query_selector(".b-post__form button[type='submit']")
            if submit_btn:
                await submit_btn.click()
                await self._page.wait_for_timeout(2000)

            logger.info(f"Отклик отправлен на заказ FL.ru: {order.title}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки отклика на FL.ru: {e}")
            return False

    async def close(self) -> None:
        """Закрытие браузера."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Браузер FL.ru закрыт")
        except Exception as e:
            logger.error(f"Ошибка закрытия браузера FL.ru: {e}")
