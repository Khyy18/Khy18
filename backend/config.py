"""Application settings loaded from environment variables."""

import os
from typing import List


class Settings:
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./bot.db"
    )
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "test-bot-token")
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    CORS_ORIGINS: List[str] = os.environ.get(
        "CORS_ORIGINS", "*"
    ).split(",")
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

    # Salary calculation constants (same as bot)
    NDFL_RATE: float = 0.13
    PFR_RATE: float = 0.22
    OMS_RATE: float = 0.051
    FSS_RATE: float = 0.029
    FSS_NS_RATE: float = 0.002
    AVG_DAYS_MONTH: float = 29.3
    BASE_FEE_PER_DAY: float = 150.0
    WORKING_DAYS_MONTH: int = 22


settings = Settings()
