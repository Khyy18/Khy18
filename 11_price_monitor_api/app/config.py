"""Конфигурация API через переменные окружения."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env."""

    # База данных
    database_url: str = "sqlite+aiosqlite:///./data/api.db"

    # JWT
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # OpenAI-совместимый API
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # ЮKassa
    yukassa_shop_id: str = ""
    yukassa_secret_key: str = ""
    yukassa_webhook_secret: str = ""  # Shared secret for webhook signature verification

    # Admin
    admin_telegram_ids: str = ""  # Comma-separated list of admin telegram IDs

    # Telegram
    telegram_admin_id: int = 0

    # Прокси
    proxy_list_file: str = ""

    # FCM
    fcm_server_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
