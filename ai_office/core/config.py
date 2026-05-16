"""Конфигурация приложения через Pydantic Settings."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env файла."""

    # OpenAI
    openai_api_key: str = Field(default="", description="API ключ OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="Модель OpenAI")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="API ключ Anthropic")

    # Groq
    groq_api_key: str = Field(default="", description="API ключ Groq")

    # LLM Multi-Provider
    llm_providers: str = Field(
        default="openai,anthropic,groq",
        description="Порядок провайдеров через запятую (fallback chain)",
    )
    llm_max_retries: int = Field(default=3, description="Макс. количество повторов на провайдер")

    # Rate Limiter and Budget
    daily_budget_usd: float = Field(default=10.0, description="Дневной бюджет в USD")
    global_rpm_limit: int = Field(default=100, description="Глобальный лимит запросов/мин")
    agent_rpm_limit: int = Field(default=20, description="Лимит запросов/мин на агента")
    enable_rate_limiter: bool = Field(default=True, description="Включить rate limiter")

    # Proactive Scheduler
    enable_proactive: bool = Field(default=True, description="Включить проактивные задачи")
    standup_hour: int = Field(default=9, description="Час ежедневного стендапа (UTC)")
    weekly_report_day: str = Field(default="monday", description="День недельного отчёта")
    overdue_check_interval_hours: int = Field(
        default=4, description="Интервал проверки просроченных задач (часы)"
    )
    health_check_interval_hours: int = Field(
        default=1, description="Интервал проверки здоровья системы (часы)"
    )

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Глобальный экземпляр настроек
settings = Settings()
