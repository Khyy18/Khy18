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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
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


# --- Торговые константы (v1 legacy) ---
# Следующие четыре константы сохранены для обратной совместимости со v1
# (стратегия RSI-cross, ai_analyst.decide). Новый код v2 опирается на
# блок "v2 constants" ниже: SYMBOLS/TIMEFRAMES/DONCHIAN/ATR/vol-targeting.
SYMBOL = "BTCUSDT"
IS_TESTNET = True
MAX_DAILY_LOSS = 0.03   # 3% от стартового эквити - суточный стоп
RISK_PER_TRADE = 0.01   # 1% на сделку

# --- v2 constants (Zenith-Control Ultimate) ---
# Мультисимвольный универсум и мультитаймфреймовое дерево.
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ("1", "60", "240", "D")  # 1м (исполнение), 1ч/4ч (сигналы), день (тренд)

# Vol-targeting: целевая годовая волатильность портфеля (20%).
TARGET_ANNUAL_VOL = 0.20

# Donchian-каналы: длинный - для входов (пробой хая/лоя N баров),
# короткий - для выходов (обратный пробой на N баров).
DONCHIAN_LONG_LOOKBACK = 20
DONCHIAN_SHORT_LOOKBACK = 10

# ATR-стопы: жёсткий стоп = 2.5 * ATR, трейлинг = 3.0 * ATR.
ATR_STOP_MULT = 2.5
ATR_TRAIL_MULT = 3.0

# Минимальная ATR(1h) в % от цены для разрешения входа по символу.
# Разные активы имеют разную волатильность: SOL в 2-3 раза волатильнее
# BTC. Единый порог 0.3% для всех либо блокирует половину BTC-сигналов
# (SOL свободно проходит), либо пропускает "мёртвые" SOL-сетапы. Отсюда
# per-symbol словарь. Если символа нет в MIN_ATR_PCT - используется
# MIN_ATR_PCT_DEFAULT.
MIN_ATR_PCT = {
    "BTCUSDT": 0.003,   # 0.30% - BTC самый крупный, волатильность ниже
    "ETHUSDT": 0.004,   # 0.40% - ETH чуть волатильнее BTC
    "SOLUSDT": 0.006,   # 0.60% - SOL существенно волатильнее
}
MIN_ATR_PCT_DEFAULT = 0.003

# Фильтр подтверждения объёмом для Donchian-пробоев.
# Объём текущей свечи должен быть >= VOLUME_CONFIRMATION_MULT * SMA(20) по
# предыдущим свечам. Если меньше - это вероятный fakeout, сигнал вето.
# 1.0 = объём не ниже среднего; 1.2 = строже (на 20% выше среднего).
VOLUME_CONFIRMATION_MULT = 1.0

# DRY_RUN: если True, бот считает сигналы и логирует намерения, но НЕ
# отправляет ордера на биржу. Для сбора статистики без риска. Читается из
# окружения; по умолчанию False (реальная торговля на demo/live).
# Guard применяется к: открытию позиций, подтягиванию трейл-стопа,
# закрытию по таймстопу, PANIC SELL из Telegram.
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes", "on")

# Таймаут на позицию (часы): если за это время сделка не закрылась
# по TP/трейлу/обратному сигналу - закрываем принудительно.
TIME_STOP_HOURS = 48

# Ярусные kill-switches (сверх суточного MAX_DAILY_LOSS = 3%).
MAX_WEEKLY_LOSS = 0.07   # 7% недельный убыток - пауза до ручного старта
MAX_DRAWDOWN = 0.15      # 15% просадка от HWM - жёсткая остановка

# TTL ответов ИИ-модулей (во избежание повторных дорогих вызовов Groq).
AI_BLACKOUT_TTL_SEC = 55 * 60      # macro-sentinel: новостной blackout, ~55 минут
AI_REGIME_TTL_SEC = 1 * 3600       # режимный классификатор: 1 час

# Расписание еженедельного пост-мортема (UTC).
# 0 = понедельник по стандарту Python (datetime.weekday()).
POSTMORTEM_DAY_UTC = 0
POSTMORTEM_HOUR_UTC = 0

# Heartbeat: как часто бот сам присылает в Telegram короткую сводку
# "я жив" со статусом. Если сообщение не пришло в срок - значит
# процесс упал или потерял сеть. 6 часов = 4 сводки в сутки.
HEARTBEAT_INTERVAL_SEC = 6 * 3600

# Риск-лимиты портфеля.
PER_SYMBOL_MAX_POSITIONS = 1        # не больше одной позиции на символ
GLOBAL_RISK_CAP = 0.03              # суммарный открытый риск не больше 3% эквити

# Correlation guard: лимит чистой направленной экспозиции в "BTC-эквиваленте".
# Каждой открытой позиции присваивается знак (long=+1, short=-1) и
# вес beta_to_btc (BTC=1.0, ETH=1.2, SOL=1.6 - средне-долгосрочные оценки).
# Если новая позиция выведет |sum(signed_qty * price * beta) / equity| за
# NET_BETA_CAP = 2.0x equity - сделка отклоняется. Это ловит сценарий
# "три одинаково-настроенные long на коррелированных альтах": формально
# каждая в пределах 1% риска, но в кризис они идут вместе.
NET_BETA_CAP = 2.0

# Graceful degradation: после N подряд верхнеуровневых ошибок в trading_loop
# (вне пер-символьной защиты) бот сам ставит торговлю на паузу и шлёт алерт
# в Telegram. Сопровождение открытых позиций продолжается, новые входы
# блокируются до ручного снятия.
GRACEFUL_DEGRADATION_THRESHOLD = 5

# PostOnly-лимитный вход: сколько ждать filла прежде чем свалиться в market IOC.
POST_ONLY_TIMEOUT_SEC = 30

# --- Биржа (переключается через переменную окружения) ---
EXCHANGE = os.getenv("EXCHANGE", "okx")

# --- Bybit V5 ---
BYBIT_BASE_URL_TESTNET = "https://api-testnet.bybit.com"
BYBIT_BASE_URL_MAINNET = "https://api.bybit.com"
BYBIT_BASE_URL = BYBIT_BASE_URL_TESTNET if IS_TESTNET else BYBIT_BASE_URL_MAINNET
BYBIT_RECV_WINDOW = "5000"

# --- Groq ---
# Используем llama-3.3-70b-versatile: большая модель (70B), сравнима по
# качеству с Gemini 2.5 Flash в задачах классификации, хорошо пишет JSON
# при response_format=json_object. Free tier: 14400 RPD / 30 RPM -
# для текущего паттерна (~50 вызовов/сутки) запаса хватает с огромным
# избытком, fallback-провайдер не требуется.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- Cerebras (резервный LLM-провайдер; OpenAI-совместимый) ---
# Бесплатный free-tier 14400 RPD. Используется только если Groq упал
# (circuit-breaker открыт) или вернул ошибку.
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# --- Gemini (последний рубеж) ---
# Используется только если Groq и Cerebras оба недоступны. Free tier
# у Gemini Flash - 1500 RPD, поэтому ставим в самый конец цепочки.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- NewsAPI ---
NEWS_API_URL = "https://newsapi.org/v2/everything"

# --- Telegram ---
TELEGRAM_API_URL = "https://api.telegram.org"


# Список обязательных переменных окружения для проверки на старте.
# Набор ключей биржи зависит от выбранного EXCHANGE: okx требует тройку
# OKX_API_KEY/SECRET/PASSPHRASE, bybit - пару BYBIT_API_KEY/SECRET.
_EXCHANGE_REQUIRED = {
    "okx": ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"),
    "bybit": ("BYBIT_API_KEY", "BYBIT_API_SECRET"),
}
_COMMON_REQUIRED = (
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GROQ_API_KEY",
    "NEWS_API_KEY",
)
REQUIRED_ENV_VARS = _EXCHANGE_REQUIRED.get(
    EXCHANGE.lower(), _EXCHANGE_REQUIRED["bybit"]
) + _COMMON_REQUIRED


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
