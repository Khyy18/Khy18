"""Конфигурация Zenith-Control Ultimate.

Все секреты читаются строго из переменных окружения через os.getenv.
Никаких значений по умолчанию для секретов не задаём. Константы торговой
системы (символ, режим testnet, лимиты риска) хранятся здесь же.
"""

import os


# --- Секреты (только из окружения) ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
_TELEGRAM_CHAT_ID_RAW = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


def _safe_int(value: str, default: int = 0) -> int:
    """Безопасное приведение строки к int (если пусто или битое значение,
    возвращаем default и не падаем на старте)."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# chat_id Telegram всегда число (приводим безопасно, чтобы модуль импортировался
# даже при отсутствии переменной - реальная проверка в main()/validate_config()).
TELEGRAM_CHAT_ID = _safe_int(_TELEGRAM_CHAT_ID_RAW, 0)


# --- Торговые константы ---
SYMBOL = "BTCUSDT"
IS_TESTNET = True
MAX_DAILY_LOSS = 0.03   # 3% от стартового эквити - суточный стоп
RISK_PER_TRADE = 0.01   # 1% на сделку

# --- Bybit V5 ---
BYBIT_BASE_URL_TESTNET = "https://api-testnet.bybit.com"
BYBIT_BASE_URL_MAINNET = "https://api.bybit.com"
BYBIT_BASE_URL = BYBIT_BASE_URL_TESTNET if IS_TESTNET else BYBIT_BASE_URL_MAINNET
BYBIT_RECV_WINDOW = "5000"

# --- Gemini ---
# Примечание: публично доступной модели "Gemini 3 Flash" не существует,
# поэтому используем актуальную быструю модель gemini-2.0-flash.
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# --- NewsAPI ---
NEWS_API_URL = "https://newsapi.org/v2/everything"

# --- Telegram ---
TELEGRAM_API_URL = "https://api.telegram.org"


# Список обязательных переменных окружения для проверки на старте.
REQUIRED_ENV_VARS = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GEMINI_API_KEY",
    "NEWS_API_KEY",
)


def validate_config() -> list[str]:
    """Возвращает список отсутствующих обязательных переменных окружения.
    Вызывается из main() - модуль должен импортироваться и при пустом .env,
    чтобы работали статические проверки и тесты компиляции."""
    missing: list[str] = []
    for name in REQUIRED_ENV_VARS:
        val = os.getenv(name, "")
        if not val:
            missing.append(name)
    # Дополнительно валидируем, что TELEGRAM_CHAT_ID приводится к int и != 0.
    if os.getenv("TELEGRAM_CHAT_ID") and TELEGRAM_CHAT_ID == 0:
        missing.append("TELEGRAM_CHAT_ID (не является целым числом)")
    return missing
