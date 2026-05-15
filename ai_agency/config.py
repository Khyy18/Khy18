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

# YooKassa платёжная система
YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_WEBHOOK_SECRET: str = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")

# Groq API
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Веб-сервер
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8080"))

# Юзернейм бота для deep links
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")

# Реферальная система
REFERRAL_BONUS_PERCENT: int = int(os.getenv("REFERRAL_BONUS_PERCENT", "10"))

# Подписки
SUBSCRIPTION_BASIC_PRICE: int = int(os.getenv("SUBSCRIPTION_BASIC_PRICE", "990"))
SUBSCRIPTION_BASIC_ORDERS: int = int(os.getenv("SUBSCRIPTION_BASIC_ORDERS", "20"))
SUBSCRIPTION_PRO_PRICE: int = int(os.getenv("SUBSCRIPTION_PRO_PRICE", "2490"))


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
    if not YOOKASSA_SHOP_ID:
        errors.append("YOOKASSA_SHOP_ID не задан. Укажите ID магазина YooKassa.")
    if not YOOKASSA_SECRET_KEY:
        errors.append("YOOKASSA_SECRET_KEY не задан. Укажите секретный ключ YooKassa.")
    return errors
