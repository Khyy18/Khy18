"""Конфигурация приложения через Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env файла."""

    # OpenAI
    openai_api_key: str = Field(default="", description="API ключ OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="Модель OpenAI")

    # JWT Auth
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for JWT token signing",
    )

    # Frontend URL (used for Stripe redirect URLs, etc.)
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Frontend application URL for redirects",
    )

    # Stripe
    stripe_secret_key: str = Field(default="", description="Stripe Secret Key")
    stripe_webhook_secret: str = Field(default="", description="Stripe Webhook Secret")
    stripe_price_starter: str = Field(default="", description="Stripe Price ID for Starter plan")
    stripe_price_pro: str = Field(default="", description="Stripe Price ID for Pro plan")
    stripe_price_agency: str = Field(default="", description="Stripe Price ID for Agency plan")

    # Super Admin
    super_admin_email: str = Field(default="", description="Super admin email address")

    # Trial
    trial_days: int = Field(default=7, description="Number of trial days for new tenants")

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

    # Zenith Crypto Trading
    zenith_api_url: str = Field(
        default="http://localhost:8002",
        description="URL сервиса Zenith Crypto Trading",
    )

    # AI Text Agency
    text_agency_api_url: str = Field(
        default="http://localhost:8003",
        description="URL сервиса AI Text Agency",
    )

    # Combo Bot
    combo_bot_api_url: str = Field(
        default="http://localhost:8004",
        description="URL сервиса Combo Bot",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Глобальный экземпляр настроек
settings = Settings()
