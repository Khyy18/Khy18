"""Конфигурация бота через переменные окружения."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из .env."""

    # Telegram
    telegram_token: str = ""
    telegram_channel_id: int = 0
    telegram_vip_channel_id: int = 0

    # OpenAI-совместимый API
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Groq
    groq_api_key: str = ""

    # Wildberries
    wb_api_token: str = ""

    # Ozon
    ozon_client_id: str = ""
    ozon_api_key: str = ""

    # Партнерские ссылки
    affiliate_tag: str = ""
    wb_affiliate_url_template: str = "https://www.wildberries.ru/catalog/{product_id}/detail.aspx?targetUrl=GP&tag={tag}"
    ozon_affiliate_url_template: str = "https://www.ozon.ru/product/{product_id}/?tag={tag}"

    # База данных
    db_path: str = "data/bot.db"

    # Интервалы парсинга (в минутах)
    parse_interval_minutes: int = 30

    # Задержки публикации
    vip_delay_seconds: int = 0
    free_delay_seconds: int = 1800  # 30 минут

    # API
    api_base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
