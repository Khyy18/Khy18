"""Создание и инициализация платформ фриланс-автоматизации."""

from __future__ import annotations

from typing import List

from freelance_automation.base import FreelancePlatform
from freelance_automation.config import (
    FLRU_COOKIES_PATH,
    KWORK_COOKIES_PATH,
    MAX_ACTION_DELAY,
    MIN_ACTION_DELAY,
    PROXY_URL,
    STEALTH_ENABLED,
)
from freelance_automation.telegram_admin import (
    append_admin_error,
    send_platform_login_failure_alert,
)
from freelance_automation.flru import FLruPlatform
from freelance_automation.kwork import KworkPlatform
from freelance_automation.stealth import StealthConfig
from logging_config import get_logger

log = get_logger(__name__)


async def build_platforms() -> List[FreelancePlatform]:
    """Создать и авторизовать доступные платформы для фриланс-сканирования."""
    stealth_config = StealthConfig(
        proxy=PROXY_URL or None,
        min_delay=MIN_ACTION_DELAY,
        max_delay=MAX_ACTION_DELAY,
        enable_stealth=STEALTH_ENABLED,
    )

    platforms: List[FreelancePlatform] = []

    kwork = KworkPlatform(stealth_config=stealth_config)
    if await kwork.login(KWORK_COOKIES_PATH):
        platforms.append(kwork)
    else:
        message = "Не удалось войти с текущими cookies."
        log.warning("kwork_login_failed", cookies_path=KWORK_COOKIES_PATH)
        append_admin_error(
            source="kwork_login",
            message=message,
            details=KWORK_COOKIES_PATH,
        )
        await send_platform_login_failure_alert("kwork", message)

    flru = FLruPlatform(stealth_config=stealth_config)
    if await flru.login(FLRU_COOKIES_PATH):
        platforms.append(flru)
    else:
        message = "Не удалось войти с текущими cookies."
        log.warning("flru_login_failed", cookies_path=FLRU_COOKIES_PATH)
        append_admin_error(
            source="flru_login",
            message=message,
            details=FLRU_COOKIES_PATH,
        )
        await send_platform_login_failure_alert("flru", message)

    if not platforms:
        log.error("no_freelance_platforms_initialized")

    return platforms
