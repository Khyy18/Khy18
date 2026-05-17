from decimal import Decimal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения. Загружается из переменных окружения или .env файла."""

    BOT_TOKEN: str = ""
    JWT_SECRET: str = "dev-secret-change-in-production"
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"
    REDIS_URL: str = "redis://localhost:6379"
    RATE_PER_MINUTE: Decimal = Decimal("5.0")

    # API ключи для внешних сервисов (опциональные, для dev режима пустые)
    LLM_API_KEY: str = ""
    STT_API_KEY: str = ""
    TTS_API_KEY: str = ""
    AVATAR_API_KEY: str = ""

    # LiveKit (для будущей интеграции видео-стриминга)
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    # --- Провайдеры AI ---
    LLM_PROVIDER: str = "anthropic"
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    TTS_PROVIDER: str = "elevenlabs"
    TTS_VOICE_ID: str = ""
    ELEVENLABS_VOICE_ID: str = ""

    # --- Оплата ---
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""

    # --- Мониторинг и безопасность ---
    SENTRY_DSN: str = ""
    ADMIN_API_KEY: str = ""

    # --- Логирование ---
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
