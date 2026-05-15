"""Конфигурация модуля спортивного арбитража.

Все секреты читаются строго из переменных окружения через os.getenv.
Никаких значений по умолчанию для секретов не задаём.
"""

import os


# --- Секреты (только из окружения) ---
ODDS_API_KEY: str = os.getenv("ODDS_API_KEY", "")
PINNACLE_USER: str = os.getenv("PINNACLE_USER", "")
PINNACLE_PASSWORD: str = os.getenv("PINNACLE_PASSWORD", "")
BETFAIR_APP_KEY: str = os.getenv("BETFAIR_APP_KEY", "")
BETFAIR_SESSION_TOKEN: str = os.getenv("BETFAIR_SESSION_TOKEN", "")
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# --- Константы арбитража ---
MIN_ARB_PROFIT: float = 1.0          # минимальная прибыль surebets (%)
MIN_VALUE_EDGE: float = 3.0          # минимальный edge для value bets (%)
MAX_BET_PCT: float = 5.0             # максимальная ставка (% от банкролла)
SCAN_INTERVAL_SEC: int = 30          # интервал сканирования (секунды)
MAX_BANKROLL_EXPOSURE: float = 20.0  # максимальная экспозиция банкролла (%)

# --- Спорты и букмекеры ---
SPORTS: list[str] = ["soccer", "tennis", "basketball"]
BOOKMAKERS: list[str] = [
    "pinnacle",
    "betfair",
    "bet365",
    "williamhill",
    "unibet",
    "marathonbet",
    "1xbet",
]

# --- Режим работы ---
DRY_RUN: bool = os.getenv("ARB_DRY_RUN", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# --- Groq (AI) ---
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL: str = "https://api.groq.com/openai/v1/chat/completions"

# --- Telegram ---
TELEGRAM_API_URL: str = "https://api.telegram.org"
