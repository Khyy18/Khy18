"""Конфигурация Zenith Funding Arbitrage Bot.

Только funding-арбитраж: directional/AI/News удалены. Ключи бирж читаются
из окружения. Константы движка — здесь.
"""

import os


# --- Биржевые секреты (только из окружения) ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_API_SECRET = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
GATE_API_KEY = os.getenv("GATE_API_KEY", "")
GATE_API_SECRET = os.getenv("GATE_API_SECRET", "")
BITGET_API_KEY = os.getenv("BITGET_API_KEY", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET", "")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")
MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET", "")
HTX_API_KEY = os.getenv("HTX_API_KEY", "")
HTX_API_SECRET = os.getenv("HTX_API_SECRET", "")
BINGX_API_KEY = os.getenv("BINGX_API_KEY", "")
BINGX_API_SECRET = os.getenv("BINGX_API_SECRET", "")

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
_TELEGRAM_CHAT_ID_RAW = os.getenv("TELEGRAM_CHAT_ID", "")


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


TELEGRAM_CHAT_ID = _safe_int(_TELEGRAM_CHAT_ID_RAW, 0)
TELEGRAM_API_URL = "https://api.telegram.org"

# --- Глобальный режим ---

# Биржа по умолчанию для key_manager и legacy-проверок (в funding-арбе используется
# несколько бирж, но один EXCHANGE остаётся для совместимости и валидации старта).
EXCHANGE = os.getenv("EXCHANGE", "bybit")
IS_TESTNET = os.getenv("IS_TESTNET", "true").strip().lower() in ("1", "true", "yes", "on")

# DRY_RUN: считаем сигналы и пишем в логи, но НЕ ставим ордера.
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes", "on")

# --- Funding scanner --------------------------------------------------

# Биржи в скане. Адаптер должен быть зарегистрирован в exchanges/__init__.py.
FUNDING_SCAN_EXCHANGES = (
    "bybit", "okx", "binance", "gate", "bitget", "mexc", "htx", "bingx",
)

# Какие символы сканировать. Все должны быть валидны на большинстве бирж
# из FUNDING_SCAN_EXCHANGES; если на какой-то символа нет — она просто
# вернёт None для этой строки (это не ошибка).
FUNDING_SCAN_SYMBOLS = (
    # Топ ликвидных.
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT",
    "TONUSDT", "AVAXUSDT", "LINKUSDT",
    # Мид-кап с исторически высокой волатильностью funding.
    "WIFUSDT", "PEPEUSDT", "SUIUSDT", "INJUSDT", "OPUSDT", "ARBUSDT",
    "JTOUSDT", "NEARUSDT", "APTUSDT", "TIAUSDT", "JUPUSDT",
)

# Период сканирования (сек).
FUNDING_SCAN_INTERVAL_SEC = 5 * 60

# Алерт: если |net_apr| какой-то записи >= порога.
FUNDING_ALERT_APR = 0.30
FUNDING_ALERT_COOLDOWN_SEC = 6 * 3600

# Гипотетическое holding для оценки fee_drag.
FUNDING_HOLDING_DAYS = 7.0

# Taker-комиссии бирж. 'default' для бирж не из словаря.
FUNDING_TAKER_FEES = {
    "bybit":   0.00055,
    "okx":     0.0005,
    "binance": 0.0004,
    "gate":    0.0005,
    "bitget":  0.0006,
    "mexc":    0.0006,
    "htx":     0.00045,
    "bingx":   0.0005,
    "default": 0.0006,
}

# Минимальные пороги для попадания в Telegram-таблицы.
FUNDING_TOP_MIN_ABS_APR = 0.05
FUNDING_CROSS_MIN_EDGE_APR = 0.10

# --- Funding executor (write) -----------------------------------------

# Master switch. По умолчанию ВЫКЛ — даже при леке .env не торгуем сами.
ARB_EXECUTOR_ENABLED = os.getenv("ARB_EXECUTOR_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on",
)

# Пары, разрешённые для входа. Пусто = все из FUNDING_SCAN_SYMBOLS.
ARB_ALLOWED_SYMBOLS: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Сколько одновременных пар держим (одна пара = один символ).
ARB_MAX_POSITIONS = 3

# Размер одной ноги в USDT.
ARB_NOTIONAL_USDT = 200.0

# Плечо. Не передаётся в ордера (используется default бирж), нужно для
# расчёта margin_required.
ARB_LEVERAGE = 3.0

# Пороги входа/выхода по net APR.
ARB_OPEN_MIN_NET_APR = 0.20    # >= 20% APR на входе
ARB_CLOSE_NET_APR = 0.05       # <= 5% APR — закрываем

# Жёсткий таймстоп.
ARB_MAX_HOLD_HOURS = 168.0     # 1 неделя

# Период тика executor'а. Должен быть >= FUNDING_SCAN_INTERVAL_SEC.
ARB_TICK_INTERVAL_SEC = 5 * 60

# Кill-switches на уровне арб-PnL. 0 = выключено.
ARB_DAILY_LOSS_USDT = float(os.getenv("ARB_DAILY_LOSS_USDT", "30") or 30)
ARB_WEEKLY_LOSS_USDT = float(os.getenv("ARB_WEEKLY_LOSS_USDT", "100") or 100)

# --- Heartbeat --------------------------------------------------------
HEARTBEAT_INTERVAL_SEC = 6 * 3600

# --- Веб-дашборд ------------------------------------------------------
DASHBOARD_ENABLED = os.getenv("DASHBOARD_ENABLED", "true").strip().lower() not in (
    "0", "false", "no", "off",
)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080") or "8080")

# --- Legacy константы (используются api_engine.py для bybit) ----------
# PostOnly: сколько ждать filla limit-ордера перед фолбэком в Market IOC.
POST_ONLY_TIMEOUT_SEC = 30
# Backward-совместимость для UI (telegram_bot читает MAX_DRAWDOWN). Эта
# величина в funding-арб-боте не используется как killswitch — оставлена
# только чтобы UI не падал при отрисовке текста подсказки.
MAX_DRAWDOWN = 0.15

# --- Bybit (для legacy validate_config) ---
BYBIT_BASE_URL_TESTNET = "https://api-testnet.bybit.com"
BYBIT_BASE_URL_MAINNET = "https://api.bybit.com"
BYBIT_BASE_URL = BYBIT_BASE_URL_TESTNET if IS_TESTNET else BYBIT_BASE_URL_MAINNET
BYBIT_RECV_WINDOW = "5000"

# --- Validation -------------------------------------------------------

# Только Telegram обязателен для старта. Биржевые ключи валидируются
# в момент попытки открытия пары (executor сам проверит баланс/auth).
_COMMON_REQUIRED = ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")

REQUIRED_ENV_VARS = _COMMON_REQUIRED


def validate_config() -> list[str]:
    """Список отсутствующих обязательных переменных окружения."""
    missing: list[str] = []
    for name in REQUIRED_ENV_VARS:
        val = os.getenv(name, "")
        if not val:
            missing.append(name)
    if os.getenv("TELEGRAM_CHAT_ID") and TELEGRAM_CHAT_ID == 0:
        missing.append("TELEGRAM_CHAT_ID (не является целым числом)")
    return missing
