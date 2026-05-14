# Zenith Funding Arbitrage Bot

Дельта-нейтральный funding-арбитраж на 8 биржах: Bybit, OKX, Binance, Gate, Bitget, MEXC, HTX, BingX.

## Что делает

1. Каждые 5 минут опрашивает funding-rate на всех биржах из `FUNDING_SCAN_EXCHANGES` по списку пар `FUNDING_SCAN_SYMBOLS`.
2. Ищет cross-exchange edge: LONG perp на бирже A + SHORT perp на бирже B по одному и тому же символу. Если `net_apr ≥ ARB_OPEN_MIN_NET_APR` (по умолчанию 20%) — открывает пару.
3. Держит до `ARB_MAX_POSITIONS` пар (3 по умолчанию). Закрывает, когда edge падает до `ARB_CLOSE_NET_APR` (5%) или истекает `ARB_MAX_HOLD_HOURS` (168 ч), либо срабатывает killswitch.
4. Шлёт уведомления в Telegram: открытие, закрытие, funding-алерты, heartbeat каждые 6 ч.
5. Опционально: read-only веб-дашборд на `DASHBOARD_PORT` (по умолчанию 8080).

## Безопасность по умолчанию

- `ARB_EXECUTOR_ENABLED=0` — автоторговля выключена. Бот только сканирует и шлёт алерты. Чтобы включить — `ARB_EXECUTOR_ENABLED=1` в `.env`.
- `IS_TESTNET=true` — testnet-эндпоинты бирж.
- `DRY_RUN=true` — считаем сигналы, но не ставим ордера.
- `ARB_DAILY_LOSS_USDT` / `ARB_WEEKLY_LOSS_USDT` — killswitch на убыток арб-движка.

## Запуск

```bash
cp .env.example .env
# заполнить TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ключи бирж
pip install -r requirements.txt
python main.py
```

## Архитектура

| Файл                  | Назначение                                      |
|-----------------------|------------------------------------------------|
| `main.py`             | event loop: scan → executor → kill → heartbeat |
| `arbitrage_engine.py` | сканер funding + расчёт net APR + cross-pairs  |
| `arb_executor.py`     | открытие/закрытие пар, учёт funding-выплат     |
| `arb_storage.py`      | SQLite-таблица arb_positions                   |
| `exchanges/*.py`      | адаптеры 8 бирж (унифицированный интерфейс)    |
| `telegram_bot.py`     | long-polling команд и инлайн-меню              |
| `dashboard.py`        | read-only HTTP-дашборд                         |
| `key_manager.py`      | ротация API-ключей через Telegram (`/setkey`)  |
| `memory.py`           | SQLite (общая БД с arb_storage)                |
| `config.py`           | константы и валидация .env                     |

## Killswitches

- **DAILY**: суточный убыток арб-движка ≥ `ARB_DAILY_LOSS_USDT` → executor выключается, открытые пары закрываются, пауза до конца UTC-суток.
- **WEEKLY**: недельный убыток ≥ `ARB_WEEKLY_LOSS_USDT` → пауза на 7 дней.
- **Manual**: кнопка PANIC в Telegram → закрытие всех пар reduce-only.

## Telegram-команды

- Кнопки в инлайн-меню: STATUS, OPEN PAIRS, FUNDING TOP, CROSS PAIRS, EXCHANGES, PAUSE/RESUME, PANIC, KEYS.
- `/setkey НАЗВАНИЕ значение` — установить API-ключ runtime (без перезапуска).
- `/delkey НАЗВАНИЕ` — удалить override (вернётся переменная окружения).

## Дашборд

`http://<host>:8080/` — статус бота, активные пары, funding-снапшот, история закрытий.
