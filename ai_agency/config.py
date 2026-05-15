"""Конфигурация AI-агентства. Все параметры читаются из переменных окружения."""

import os
from typing import List


# Токен клиентского бота
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Токен админского бота
TELEGRAM_ADMIN_BOT_TOKEN: str = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN", "")

# Telegram ID администратора
ADMIN_TELEGRAM_ID: int = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# Ключ OpenAI API
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# Модель по умолчанию
DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# Путь к базе данных SQLite
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "agency.db")


def validate_config() -> List[str]:
    """
    Проверить наличие обязательных переменных окружения.
    Возвращает список ошибок (пустой если все ОК).
    """
    errors: List[str] = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN не задан. Укажите токен клиентского бота.")
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY не задан. Укажите ключ OpenAI API.")
    return errors
