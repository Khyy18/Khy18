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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
