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
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Режим торговли: true = OKX Demo (виртуальный баланс, x-simulated-trading),
# false = OKX Mainnet (реальные деньги). Читается из env на старте процесса.
# Переключение через кнопку "🏦 Демо/Реал" в Telegram делает запись в .env
# и SIGTERM - systemd перезапустит процесс с новым значением.
IS_TESTNET = os.getenv("IS_TESTNET", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# OKX ключи: демо и реал хранятся раздельно в .env, активная тройка
# выбирается ниже по значению IS_TESTNET. Код адаптера (exchanges/okx.py)
# и api_engine обращаются к OKX_API_KEY / _SECRET / _PASSPHRASE напрямую
# и не знают о существовании двух наборов - вся маршрутизация здесь.
OKX_API_KEY_DEMO = os.getenv("OKX_API_KEY", "")
OKX_API_SECRET_DEMO = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE_DEMO = os.getenv("OKX_PASSPHRASE", "")

OKX_API_KEY_REAL = os.getenv("OKX_API_KEY_REAL", "")
OKX_API_SECRET_REAL = os.getenv("OKX_API_SECRET_REAL", "")
OKX_PASSPHRASE_REAL = os.getenv("OKX_PASSPHRASE_REAL", "")

if IS_TESTNET:
    OKX_API_KEY = OKX_API_KEY_DEMO
    OKX_API_SECRET = OKX_API_SECRET_DEMO
    OKX_PASSPHRASE = OKX_PASSPHRASE_DEMO
else:
    OKX_API_KEY = OKX_API_KEY_REAL
    OKX_API_SECRET = OKX_API_SECRET_REAL
    OKX_PASSPHRASE = OKX_PASSPHRASE_REAL


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
MAX_DAILY_LOSS = 0.03   # 3% от стартового эквити - суточный стоп
RISK_PER_TRADE = 0.01   # 1% на сделку

# --- v2 constants (Zenith-Control Ultimate) ---
# Мультисимвольный универсум и мультитаймфреймовое дерево.
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
]
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
    "BNBUSDT": 0.004,   # 0.40% - BNB близко к ETH по волатильности
    "XRPUSDT": 0.006,   # 0.60% - XRP более рывковый, нужен фильтр повыше
    "DOGEUSDT": 0.008,  # 0.80% - meme-coin, высокая шумность
    "AVAXUSDT": 0.006,  # 0.60% - L1 alt, сравнимо с SOL
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
AI_REGIME_TTL_SEC = 30 * 60        # режимный классификатор: 30 минут

# AI-veto gate перед открытием сделки.
# "off"    - gate отключён, всегда approve без вызова Groq.
# "shadow" - gate вызывается на каждое намерение, решение ЛОГИРУЕТСЯ
#            в Telegram и stdout как "would approve/veto", но НЕ применяется:
#            сделка всегда открывается если стратегия и фильтры дали OK.
#            Режим для сбора статистики без влияния на торговлю.
# "active" - gate применяется: veto блокирует сделку с записью в rejected_checks.
# Fail-CLOSED: на любой ошибке Groq (сеть, таймаут, невалидный JSON) решение
# считается "error" и в active-режиме ТРАКТУЕТСЯ КАК veto (сделка НЕ открывается).
# В shadow-режиме ошибка только логируется.
AI_TRADE_GATE_MODE = os.getenv("AI_TRADE_GATE_MODE", "shadow").strip().lower()
# Таймаут одного вызова gate (сек). Короткий, чтобы не тормозить торговый тик.
AI_TRADE_GATE_TIMEOUT = 8
# Сколько часов новостей NewsAPI подмешивать в prompt.
AI_TRADE_GATE_NEWS_HOURS = 6
# Сколько заголовков максимум класть в prompt (ограничение размера).
AI_TRADE_GATE_NEWS_LIMIT = 10

# Расписание еженедельного пост-мортема (UTC).
# 0 = понедельник по стандарту Python (datetime.weekday()).
POSTMORTEM_DAY_UTC = 0
POSTMORTEM_HOUR_UTC = 0

# Heartbeat: как часто бот сам присылает в Telegram короткую сводку
# "я жив" со статусом. Если сообщение не пришло в срок - значит
# процесс упал или потерял сеть. 6 часов = 4 сводки в сутки.
HEARTBEAT_INTERVAL_SEC = 6 * 3600

# Telegram-уведомления. Оба флага читаются из .env; дефолт True, чтобы
# существующие деплои сразу получали события без ручной правки .env.
# NOTIFY_ON_TRADE_OPEN — карточка сделки при открытии позиции.
# NOTIFY_ON_GATE_ERROR_BLOCK — уведомление, когда стратегия хотела
# открыть сделку, но AI-Gate в active-режиме заблокировал её из-за
# verdict=error (Groq недоступен, fail-CLOSED). В shadow/off такое
# уведомление не отправляется — в этих режимах error не блокирует.
NOTIFY_ON_TRADE_OPEN = os.getenv("NOTIFY_ON_TRADE_OPEN", "true").strip().lower() in (
    "1", "true", "yes", "on",
)
NOTIFY_ON_GATE_ERROR_BLOCK = os.getenv("NOTIFY_ON_GATE_ERROR_BLOCK", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# Риск-лимиты портфеля.
PER_SYMBOL_MAX_POSITIONS = 1        # не больше одной позиции на символ
GLOBAL_RISK_CAP = 0.04              # суммарный открытый риск не больше 4% эквити

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
    чтобы работали статические проверки и тесты компиляции.

    Для EXCHANGE=okx реал-ключи (OKX_API_KEY_REAL/_SECRET_REAL/_PASSPHRASE_REAL)
    считаются опциональными: пользователь может их заполнить потом через
    кнопку "🔑 КЛЮЧИ API" в Telegram. Но если IS_TESTNET=false и реал-ключи
    пустые - это явная ошибка конфигурации, падаем с понятным сообщением.
    """
    missing: list[str] = []
    for name in REQUIRED_ENV_VARS:
        val = os.getenv(name, "")
        if not val:
            missing.append(name)
    # Дополнительно валидируем, что TELEGRAM_CHAT_ID приводится к int и != 0.
    if os.getenv("TELEGRAM_CHAT_ID") and TELEGRAM_CHAT_ID == 0:
        missing.append("TELEGRAM_CHAT_ID (не является целым числом)")
    # Если режим РЕАЛ, то реал-тройка обязана быть заполнена.
    if EXCHANGE.lower() == "okx" and not IS_TESTNET and not OKX_API_KEY_REAL:
        missing.append(
            "OKX_API_KEY_REAL (IS_TESTNET=false, но OKX_API_KEY_REAL не заполнен)"
        )
    return missing
