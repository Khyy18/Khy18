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

# White-label персона
BOT_PERSONA_NAME: str = os.getenv("BOT_PERSONA_NAME", "Алиса")
BOT_PERSONA_GREETING: str = os.getenv(
    "BOT_PERSONA_GREETING", "Привет! Я Алиса, ваш персональный менеджер."
)

# Канал для публикации кейсов
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")

# Kwork парсер
KWORK_KEYWORDS: str = os.getenv("KWORK_KEYWORDS", "копирайтинг,рерайт,SEO,перевод")

# Мульти-бот архитектура (JSON-строка)
NICHE_BOTS: str = os.getenv("NICHE_BOTS", "[]")

# REST API
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# Подписки
SUBSCRIPTION_BASIC_PRICE: int = int(os.getenv("SUBSCRIPTION_BASIC_PRICE", "990"))
SUBSCRIPTION_BASIC_ORDERS: int = int(os.getenv("SUBSCRIPTION_BASIC_ORDERS", "20"))
SUBSCRIPTION_PRO_PRICE: int = int(os.getenv("SUBSCRIPTION_PRO_PRICE", "2490"))

# Sentry (опционально)
SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

# Очередь заказов
QUEUE_MAX_SIZE: int = int(os.getenv("QUEUE_MAX_SIZE", "100"))
QUEUE_WORKERS: int = int(os.getenv("QUEUE_WORKERS", "3"))

# Telegram Stars
STARS_TO_RUB_RATE: float = float(os.getenv("STARS_TO_RUB_RATE", "1.5"))

# Аналитика
GOOGLE_ANALYTICS_ID: str = os.getenv("GOOGLE_ANALYTICS_ID", "")
YANDEX_METRIKA_ID: str = os.getenv("YANDEX_METRIKA_ID", "")

# Логирование
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/agency.log")

# Бэкапы
BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
BACKUP_KEEP_COUNT: int = int(os.getenv("BACKUP_KEEP_COUNT", "7"))

# OpenAI стоимость токенов
OPENAI_TOKEN_COST_PER_1K: float = float(os.getenv("OPENAI_TOKEN_COST_PER_1K", "0.03"))

# Партнёрская программа
PARTNER_COMMISSION_PERCENT: int = int(os.getenv("PARTNER_COMMISSION_PERCENT", "10"))

# Семантический кеш
CACHE_TTL_DAYS: int = int(os.getenv("CACHE_TTL_DAYS", "7"))
CACHE_SIMILARITY_THRESHOLD: float = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))

# Воронка продаж
FUNNEL_ENABLED: bool = os.getenv("FUNNEL_ENABLED", "True").lower() in ("true", "1", "yes")

# Рекламный бюджет
AD_BUDGET_PERCENT: int = int(os.getenv("AD_BUDGET_PERCENT", "30"))

# Telega.in API
TELEGA_IN_API_KEY: str = os.getenv("TELEGA_IN_API_KEY", "")

# Webhook
WEBHOOK_SECRET_KEY: str = os.getenv("WEBHOOK_SECRET_KEY", "")

# Админ-панель
ADMIN_DASHBOARD_PASSWORD: str = os.getenv("ADMIN_DASHBOARD_PASSWORD", "")

# Mini App
MINI_APP_URL: str = os.getenv("MINI_APP_URL", "")

# Stripe (международные платежи)
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# NOWPayments (крипто-платежи)
NOWPAYMENTS_API_KEY: str = os.getenv("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET: str = os.getenv("NOWPAYMENTS_IPN_SECRET", "")

# Контент-ферма (автопостинг в каналы)
CONTENT_FARM_CHANNELS: str = os.getenv("CONTENT_FARM_CHANNELS", "[]")

# White-label система
WHITELABEL_ENABLED: bool = os.getenv("WHITELABEL_ENABLED", "False").lower() in ("true", "1", "yes")

# USD to RUB exchange rate
USD_TO_RUB_RATE: float = float(os.getenv("USD_TO_RUB_RATE", "90.0"))

# Demand pricing
DEMAND_SURGE_THRESHOLD: int = int(os.getenv("DEMAND_SURGE_THRESHOLD", "10"))
DEMAND_DISCOUNT_THRESHOLD: int = int(os.getenv("DEMAND_DISCOUNT_THRESHOLD", "2"))

# Loyalty system
LOYALTY_ENABLED: bool = os.getenv("LOYALTY_ENABLED", "True").lower() in ("true", "1", "yes")

# Retargeting
RETARGETING_ENABLED: bool = os.getenv("RETARGETING_ENABLED", "True").lower() in ("true", "1", "yes")

# WebSocket dashboard auth
WS_AUTH_TOKEN: str = os.getenv("WS_AUTH_TOKEN", "")

# --- Autopilot settings ---

# Автоматическая отправка откликов на лиды (Kwork)
AUTO_RESPOND_LEADS: bool = os.getenv("AUTO_RESPOND_LEADS", "False").lower() in ("true", "1", "yes")

# Автопилот рекламы (автоматическое размещение через Telega.in)
AD_AUTOPILOT: bool = os.getenv("AD_AUTOPILOT", "False").lower() in ("true", "1", "yes")

# Автомодерация отзывов (публикация без ручного одобрения)
AUTO_MODERATE_REVIEWS: bool = os.getenv("AUTO_MODERATE_REVIEWS", "True").lower() in ("true", "1", "yes")

# Час отправки ежедневного отчёта владельцу (0-23)
DAILY_REPORT_HOUR: int = int(os.getenv("DAILY_REPORT_HOUR", "21"))

# --- Multi-provider LLM Router ---

# Anthropic API
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# Together.ai API
TOGETHER_API_KEY: str = os.getenv("TOGETHER_API_KEY", "")

# --- Kwork human-like settings ---

# Warmup period (days from registration)
KWORK_WARMUP_DAYS: int = int(os.getenv("KWORK_WARMUP_DAYS", "14"))

# Max daily auto-responses on Kwork
KWORK_MAX_DAILY_RESPONSES: int = int(os.getenv("KWORK_MAX_DAILY_RESPONSES", "7"))

# Working hours (only respond between these hours)
KWORK_WORK_HOURS_START: int = int(os.getenv("KWORK_WORK_HOURS_START", "9"))
KWORK_WORK_HOURS_END: int = int(os.getenv("KWORK_WORK_HOURS_END", "22"))

# --- FL.ru parser ---

# FL.ru keywords (comma-separated, defaults to KWORK_KEYWORDS)
FL_KEYWORDS: str = os.getenv("FL_KEYWORDS", "")

# Max daily auto-responses on FL.ru
FL_MAX_DAILY_RESPONSES: int = int(os.getenv("FL_MAX_DAILY_RESPONSES", "7"))

# --- Telegram chat parser ---

# Comma-separated chat IDs to monitor
TG_MONITOR_CHATS: str = os.getenv("TG_MONITOR_CHATS", "")

# Max responses per hour per chat
TG_MAX_RESPONSES_PER_HOUR: int = int(os.getenv("TG_MAX_RESPONSES_PER_HOUR", "3"))

# Telegram userbot session (for pyrogram)
TELEGRAM_USERBOT_SESSION: str = os.getenv("TELEGRAM_USERBOT_SESSION", "")

# Telegram API credentials (for pyrogram userbot)
TELEGRAM_API_ID: str = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")

# --- Database & Cache backends ---

# Redis URL (optional)
REDIS_URL: str = os.getenv("REDIS_URL", "")

# Database backend: sqlite or postgres
DATABASE_BACKEND: str = os.getenv("DATABASE_BACKEND", "sqlite")

# PostgreSQL connection URL (for postgres backend)
DATABASE_URL: str = os.getenv("DATABASE_URL", "")


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
