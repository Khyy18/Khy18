"""Configuration for the Telegram Admin Bot."""
from __future__ import annotations

import os


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_ADMIN_BOT_TOKEN", "")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost/outbound_sales"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Comma-separated list of Telegram user IDs allowed to use admin commands.
# Example: TELEGRAM_ADMIN_CHAT_IDS=123456789,987654321
_raw_admin_ids = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "")
ADMIN_CHAT_IDS: list[int] = [
    int(x.strip()) for x in _raw_admin_ids.split(",") if x.strip()
]
