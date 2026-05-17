"""Configuration for the Telegram Admin Bot."""

import os


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_ADMIN_BOT_TOKEN", "")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost/outbound_sales"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
