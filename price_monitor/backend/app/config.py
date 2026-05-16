"""Конфигурация приложения через переменные окружения."""
from __future__ import annotations


from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env."""

    # База данных
    database_url: str = "sqlite+aiosqlite:///./data/api.db"
    postgresql_url: str = "postgresql+asyncpg://price_monitor:price_monitor_secret@localhost:5432/price_monitor"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Telegram
    telegram_bot_token: str = ""
    telegram_admin_id: int = 0
    telegram_channel_id: int = 0

    # Email (Resend/Mailgun)
    email_api_key: str = ""
    email_api_url: str = "https://api.resend.com"
    email_from: str = "Price Monitor <noreply@your-domain.com>"

    # OpenAI-совместимый API
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # ЮKassa
    yukassa_shop_id: str = ""
    yukassa_secret_key: str = ""
    yukassa_webhook_secret: str = ""

    # Sentry
    sentry_dsn: str = ""

    # Internal API key for service-to-service calls
    internal_api_key: str = ""

    # Admin
    admin_telegram_ids: str = ""

    # Прокси
    proxy_list_file: str = ""

    # FCM
    fcm_server_key: str = ""

    # Партнерская программа
    partner_commission_percent: float = 5.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
