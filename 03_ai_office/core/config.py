"""Конфигурация приложения через Pydantic Settings."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env файла."""

    # OpenAI
    openai_api_key: str = Field(default="", description="API ключ OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="Модель OpenAI")

    # Telegram
    telegram_api_id: int = Field(default=0, description="Telegram API ID")
    telegram_api_hash: str = Field(default="", description="Telegram API Hash")
    telegram_bot_token: str = Field(default="", description="Токен Telegram бота")
    target_chat_id: int = Field(default=0, description="ID целевого чата")

    # GitHub
    github_token: str = Field(default="", description="GitHub Personal Access Token")

    # Аутентификация
    skip_telegram_auth: bool = Field(
        default=True, description="Пропуск аутентификации Telegram (dev-режим)"
    )

    # База данных
    database_url: str = Field(
        default="sqlite+aiosqlite:///./ai_office.db",
        description="URL подключения к базе данных",
    )

    # Outbound Sales
    outbound_sales_api_url: str = Field(
        default="http://localhost:8001",
        description="URL сервиса AI Outbound Sales",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Глобальный экземпляр настроек
settings = Settings()
