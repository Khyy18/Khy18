"""Скраперы коэффициентов для мягких букмекеров.

Базовый класс и заготовки для скрапинга bet365, Unibet и др.
Для реальной работы требуется: Playwright, прокси, anti-detect browser.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional


class BookmakerScraper(ABC):
    """Базовый класс для скрапинга коэффициентов мягких БК.

    Подклассы реализуют login() и get_odds() для конкретных букмекеров.
    Для реальной работы нужен Playwright + residential прокси + anti-detect.
    """

    def __init__(self, proxy_url: Optional[str] = None) -> None:
        self._proxy_url = proxy_url
        self._logged_in: bool = False

    @abstractmethod
    async def login(self, username: str, password: str) -> bool:
        """Авторизация на сайте букмекера."""
        ...

    @abstractmethod
    async def get_odds(self, sport: str, event_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Получить коэффициенты по виду спорта или конкретному событию."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Закрыть браузер/сессию."""
        ...


class Bet365Scraper(BookmakerScraper):
    """Заготовка для bet365. Требует: Playwright, residential proxy, anti-detect browser.

    Bet365 активно борется с ботами:
    - Обфускация DOM
    - Fingerprint detection
    - Rate limiting по IP
    - Captcha при подозрительной активности
    """

    async def login(self, username: str, password: str) -> bool:
        raise NotImplementedError(
            "Bet365Scraper требует Playwright + anti-detect browser. "
            "Реализация недоступна без headless-браузера и residential прокси."
        )

    async def get_odds(self, sport: str, event_id: Optional[str] = None) -> list[dict[str, Any]]:
        raise NotImplementedError("Bet365Scraper.get_odds() не реализован.")

    async def close(self) -> None:
        pass


class UnibetScraper(BookmakerScraper):
    """Заготовка для Unibet. Требует: Playwright + прокси.

    Unibet менее агрессивен в anti-bot, но все равно требует:
    - Headless browser с правильным user-agent
    - Residential прокси (datacenter blocked)
    - Cookie/session management
    """

    async def login(self, username: str, password: str) -> bool:
        raise NotImplementedError(
            "UnibetScraper требует Playwright + прокси. "
            "Реализация недоступна без headless-браузера."
        )

    async def get_odds(self, sport: str, event_id: Optional[str] = None) -> list[dict[str, Any]]:
        raise NotImplementedError("UnibetScraper.get_odds() не реализован.")

    async def close(self) -> None:
        pass
