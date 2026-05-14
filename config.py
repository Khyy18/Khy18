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
# Можно переопределить через env: BYBIT_TAKER_FEE=0.00045 и т.д.
def _fee(env_name: str, default: float) -> float:
    raw = os.getenv(env_name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


FUNDING_TAKER_FEES = {
    "bybit":   _fee("BYBIT_TAKER_FEE",   0.00055),
    "okx":     _fee("OKX_TAKER_FEE",     0.0005),
    "binance": _fee("BINANCE_TAKER_FEE", 0.0004),
    "gate":    _fee("GATE_TAKER_FEE",    0.0005),
    "bitget":  _fee("BITGET_TAKER_FEE",  0.0006),
    "mexc":    _fee("MEXC_TAKER_FEE",    0.0006),
    "htx":     _fee("HTX_TAKER_FEE",     0.00045),
    "bingx":   _fee("BINGX_TAKER_FEE",   0.0005),
    "default": _fee("DEFAULT_TAKER_FEE", 0.0006),
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

# Killswitch в процентах от стартового equity (доля). 0 = выключено.
# Триггерим при max(USDT-лимит, equity * pct-лимит) — то, что больше.
# Это даёт корректное масштабирование при росте/падении капитала.
ARB_DAILY_LOSS_PCT = float(os.getenv("ARB_DAILY_LOSS_PCT", "0.02") or 0.02)
ARB_WEEKLY_LOSS_PCT = float(os.getenv("ARB_WEEKLY_LOSS_PCT", "0.06") or 0.06)

# Directional stop-loss: закрыть пару, если непосредственный убыток по
# двум ногам (без funding) превысил X% от notional. Защита от каскадов
# ликвидаций — funding-edge может всё ещё быть положительным, а цена
# уже ушла так, что мы под margin-call.
ARB_DIRECTIONAL_STOP_PCT = float(os.getenv("ARB_DIRECTIONAL_STOP_PCT", "0.03") or 0.03)

# Margin guard: если на любой бирже свободного USDT меньше чем
# (1 - ratio) * margin_required — превентивно закрываем позицию.
# 0.7 = триггерим при использовании > 70% margin.
ARB_MARGIN_RATIO_GUARD = float(os.getenv("ARB_MARGIN_RATIO_GUARD", "0.70") or 0.70)
MARGIN_GUARD_INTERVAL_SEC = 120.0

# Per-exchange leg cap: не больше N ног на одной бирже одновременно.
# С ARB_MAX_POSITIONS=3 и MAX_LEGS_PER_EXCHANGE=2 — даже если все 3 пары
# затрагивают одну биржу, на ней будут максимум 2 ноги (одна пара
# принудительно встанет на другой паре бирж).
ARB_MAX_LEGS_PER_EXCHANGE = int(os.getenv("ARB_MAX_LEGS_PER_EXCHANGE", "2") or 2)

# Атомарное открытие пары: тайм-аут на каждую ногу. После — rollback.
ARB_OPEN_TIMEOUT_SEC = float(os.getenv("ARB_OPEN_TIMEOUT_SEC", "12") or 12)

# Liquidity check перед открытием: максимальный spread (best_ask - best_bid)
# в bps на каждой бирже. 15 bps = 0.15%. Если шире — пропускаем кандидата.
ARB_MAX_SPREAD_BPS = float(os.getenv("ARB_MAX_SPREAD_BPS", "15") or 15)

# Pre-funding bonus: окно (минуты) до next_funding_ts на SHORT-ноге.
# Если funding-tick близко — кандидат получает бонус ×1.0..1.5 к скору.
ARB_PREFUNDING_BONUS_WINDOW_MIN = float(
    os.getenv("ARB_PREFUNDING_BONUS_WINDOW_MIN", "30") or 30
)

# Anti-spike фильтр: если текущий APR > среднего за окно × множитель —
# считаем спайком и пропускаем. 2.0 = текущий вдвое выше среднего за 24h.
FUNDING_SPIKE_RATIO = float(os.getenv("FUNDING_SPIKE_RATIO", "2.5") or 2.5)
FUNDING_HISTORY_WINDOW_HOURS = float(
    os.getenv("FUNDING_HISTORY_WINDOW_HOURS", "24") or 24
)

# Circuit breaker: окно подсчёта ошибок, порог, cooldown.
BREAKER_WINDOW_SEC = float(os.getenv("BREAKER_WINDOW_SEC", "60") or 60)
BREAKER_FAIL_THRESHOLD = int(os.getenv("BREAKER_FAIL_THRESHOLD", "5") or 5)
BREAKER_COOLDOWN_SEC = float(os.getenv("BREAKER_COOLDOWN_SEC", "600") or 600)

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
