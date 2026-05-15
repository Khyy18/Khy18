"""Application settings loaded from environment variables."""

import os
from typing import List

# Default CORS origins for development
_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:8080"


def _parse_cors_origins() -> List[str]:
    """Parse CORS_ORIGINS from environment variable (comma-separated)."""
    raw = os.environ.get("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins if origins else ["http://localhost:3000", "http://localhost:8080"]


class Settings:
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./bot.db"
    )
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "test-bot-token")
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    CORS_ORIGINS: List[str] = _parse_cors_origins()
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
