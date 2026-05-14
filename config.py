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

# Auto-recovery: если бот в degraded, раз в RECOVERY_PROBE_INTERVAL_SEC
# пробуем дёрнуть EXCHANGE.get_server_time. На успехе - bot_running=True
# и degraded=False, без ручного вмешательства. 5 минут - компромисс
# между "быстро возобновить торговлю" и "не долбить упавшую биржу".
RECOVERY_PROBE_INTERVAL_SEC = 5 * 60

# PostOnly-лимитный вход: сколько ждать filла прежде чем свалиться в market IOC.
POST_ONLY_TIMEOUT_SEC = 30

# --- Funding rate / арбитражный сканер (Фаза 1) ---
# Биржи, по которым опрашиваем funding. Должны быть зарегистрированы в
# exchanges/__init__.py. Если адаптер не реализует get_funding_info -
# будет молча пропущен.
FUNDING_SCAN_EXCHANGES = ("bybit", "okx")

# Какие символы сканировать. По умолчанию - топ ликвидных перпов на обеих
# биржах (BTC/ETH/SOL уже в SYMBOLS, плюс несколько популярных альтов).
# Все символы должны быть валидны на ВСЕХ биржах из FUNDING_SCAN_EXCHANGES,
# иначе по части бирж получим None в этой строке (не страшно, просто шум).
FUNDING_SCAN_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
    "TONUSDT",
    "AVAXUSDT",
    "LINKUSDT",
)

# Период сканирования в секундах. 5 минут - компромисс между свежестью
# данных и нагрузкой на публичные эндпоинты бирж (без auth, но rate
# limit всё равно есть). Funding меняется не быстрее минут.
FUNDING_SCAN_INTERVAL_SEC = 5 * 60

# Порог автоалерта: если |net_apr| какой-то записи >= FUNDING_ALERT_APR,
# в Telegram прилетает push. По дефолту 0.30 = 30% годовых после комиссий.
# Это уже "интересно посмотреть", но не "точно жирно".
FUNDING_ALERT_APR = 0.30

# Чтобы не спамить одинаковыми алертами, после каждой отправки ставим
# cooldown по конкретной (биржа, символ) ключу.
FUNDING_ALERT_COOLDOWN_SEC = 6 * 3600  # 6 часов

# Гипотетическое время удержания позиции при оценке fee_drag.
# 7 дней означает: предполагаем, что распределим 2*taker_fee на неделю.
# Чем меньше holding_days, тем строже фильтр - так fee_drag быстрее
# съедает funding.
FUNDING_HOLDING_DAYS = 7.0

# Taker-комиссии на разных биржах. Используются в arbitrage_engine для
# расчёта fee_drag. Числа - typical для VIP0 без BNB-скидки и т.п.
# Реальные у пользователя могут быть ниже (промо, объёмная скидка) -
# можно править. 'default' применяется к биржам не из словаря.
FUNDING_TAKER_FEES = {
    "bybit": 0.00055,    # 0.055% taker (linear perp, VIP0)
    "okx": 0.0005,       # 0.05% taker (SWAP, regular)
    "default": 0.0006,
}

# Минимальный порог попадания в "TOP FUNDING" таблицу (по |net_apr|).
# 5% APR после комиссий = на 1М₽ примерно 4k₽/мес. Ниже - мусор.
FUNDING_TOP_MIN_ABS_APR = 0.05

# Минимальный edge для попадания в кросс-биржевую таблицу.
FUNDING_CROSS_MIN_EDGE_APR = 0.10  # 10% APR после комиссий с обеих ног

# --- Funding-rate ARB EXECUTOR (Фаза 3, write) ---
# По умолчанию executor ВЫКЛЮЧЕН. Это safety-net: даже если кто-то сольёт
# репозиторий с .env по умолчанию, бот не начнёт сам торговать.
# Включается явно в .env: ARB_EXECUTOR_ENABLED=1
ARB_EXECUTOR_ENABLED = os.getenv("ARB_EXECUTOR_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on",
)

# Какие символы разрешены для арб-входа. Пустой список = разрешены ВСЕ
# из FUNDING_SCAN_SYMBOLS. Имеет смысл начинать с одного-двух самых
# ликвидных, чтобы spread/slippage был минимален.
ARB_ALLOWED_SYMBOLS: list[str] = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

# Размер одной ноги в USDT. На двух биржах нужно по этой сумме (ну, по
# ARB_NOTIONAL_USDT / ARB_LEVERAGE маржи + 10% запас). Старт с 200 -
# это около 1% от типового тестового депозита, минимально безопасно.
# Реально надо подбирать под minNotional бирж; на BTC notional<200
# у OKX иногда невалиден (1 контракт = 0.01 BTC ~ $700 при 70k).
ARB_NOTIONAL_USDT = 200.0

# Плечо на perp. Не задаётся в самих ордерах, биржа использует
# default-leverage аккаунта. Здесь только для расчёта маржи и проверки
# что баланса хватит.
ARB_LEVERAGE = 3.0

# Порог открытия: net APR (после ВСЕХ комиссий, holding=ARB_HOLDING_DAYS)
# должен быть >= 20%. Ниже - не открываем.
ARB_OPEN_MIN_NET_APR = 0.20

# Порог закрытия: если net APR упал до 5% (или развернулся), закрываемся.
# Зазор между OPEN и CLOSE (20% vs 5%) - hysteresis, чтобы не дёргаться
# на каждой осцилляции.
ARB_CLOSE_NET_APR = 0.05

# Жёсткий тайм-стоп: не держим дольше N часов даже если edge ОК.
# 168 = 1 неделя. Идея - принудительно ребалансироваться, чтобы не
# зависнуть на одной паре навечно при changing rate.
ARB_MAX_HOLD_HOURS = 168.0

# Период тика executor'а (секунды). Должен быть >= FUNDING_SCAN_INTERVAL_SEC,
# потому что executor работает с кэшированным snapshot.
ARB_TICK_INTERVAL_SEC = 5 * 60

# Биржа (переключается через переменную окружения)
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
