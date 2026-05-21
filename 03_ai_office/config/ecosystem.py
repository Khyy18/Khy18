"""
Конфигурация экосистемы сервисов.

Для единого сервера — все на localhost с разными портами.
В продакшене заменить на реальные адреса через переменные окружения.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class EcosystemConfig:
    """Адреса и настройки всех сервисов экосистемы."""

    # API-адреса сервисов
    price_monitor_api_url: str = field(
        default_factory=lambda: os.getenv("PRICE_MONITOR_API_URL", "http://localhost:8000")
    )
    outbound_api_url: str = field(
        default_factory=lambda: os.getenv("OUTBOUND_API_URL", "http://localhost:8001")
    )
    text_agency_api_url: str = field(
        default_factory=lambda: os.getenv("TEXT_AGENCY_API_URL", "http://localhost:8002")
    )
    office_api_url: str = field(
        default_factory=lambda: os.getenv("OFFICE_API_URL", "http://localhost:8003")
    )

    # Telegram
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("OFFICE_TG_BOT_TOKEN", "")
    )
    admin_chat_id: str = field(
        default_factory=lambda: os.getenv("OFFICE_ADMIN_CHAT_ID", "")
    )

    # Таймауты (секунды)
    request_timeout: float = 30.0
    campaign_send_timeout: float = 60.0


# Синглтон конфигурации
ecosystem_config = EcosystemConfig()
