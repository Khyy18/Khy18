"""Модуль антидетекта для Playwright: stealth, прокси, ротация User-Agent."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

try:
    from playwright_stealth import stealth_async  # type: ignore
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

# Реалистичные User-Agent строки (Chrome/Firefox, Windows/macOS/Linux)
_DEFAULT_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


@dataclass
class StealthConfig:
    """Конфигурация антидетекта для Playwright."""

    proxy: Optional[str] = None  # SOCKS5/HTTP URL прокси
    user_agents: list[str] = field(default_factory=lambda: list(_DEFAULT_USER_AGENTS))
    min_delay: float = 1.0  # Минимальная задержка (секунды)
    max_delay: float = 3.0  # Максимальная задержка (секунды)
    enable_stealth: bool = True  # Включить playwright-stealth


async def apply_stealth(page) -> None:
    """Применить playwright-stealth к странице (если библиотека установлена)."""
    if _HAS_STEALTH:
        await stealth_async(page)


async def random_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """Случайная задержка для имитации поведения человека."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


def get_random_user_agent(config: StealthConfig) -> str:
    """Получить случайный User-Agent из конфигурации."""
    return random.choice(config.user_agents)


def get_random_viewport() -> dict[str, int]:
    """Получить случайный размер viewport с небольшим отклонением."""
    base_width = 1920
    base_height = 1080
    width = base_width + random.randint(-100, 100)
    height = base_height + random.randint(-60, 60)
    return {"width": width, "height": height}
