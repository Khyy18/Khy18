"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Bot configuration from .env file."""

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    CHANGENOW_API_KEY: str = os.getenv("CHANGENOW_API_KEY", "")
    EXOLIX_API_KEY: str = os.getenv("EXOLIX_API_KEY", "")
    ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
    MARKUP_PERCENT: float = float(os.getenv("MARKUP_PERCENT", "1.5"))
    EXCHANGE_TIMEOUT_MINUTES: int = int(os.getenv("EXCHANGE_TIMEOUT_MINUTES", "60"))
    RATE_CACHE_TTL: int = int(os.getenv("RATE_CACHE_TTL", "30"))

    # API base URLs
    CHANGENOW_BASE_URL: str = "https://api.changenow.io/v2"
    EXOLIX_BASE_URL: str = "https://exolix.com/api/v2"

    # Polling interval for status checks (seconds)
    STATUS_POLL_INTERVAL: int = int(os.getenv("STATUS_POLL_INTERVAL", "30"))


config = Config()
