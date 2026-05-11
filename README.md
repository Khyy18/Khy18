# Zenith-Control Ultimate

Гибридная асинхронная криптоторговая система на Python 3.11. Работает на
бирже Bybit (V5 Unified Trading Account), управляется Telegram-терминалом,
принимает решения с помощью Google Gemini и использует новостной контекст
от NewsAPI. Память сделок ведётся в SQLite.

## Возможности

- Ручная HMAC-SHA256 подпись Bybit V5 (без pybit).
- Стратегия на чистом Python: EMA(200), RSI(14), ATR(14) - без pandas/numpy.
- ИИ-аналитик Gemini как финальный фильтр входа (вход только при
  `decision == APPROVE` и `confidence > 85`).
- Перевод стоп-лосса в безубыток при +1.0% и трейлинг тейк-профит при +1.5%.
- Суточный стоп по убыткам `MAX_DAILY_LOSS = 3%`, риск на сделку `1%`.
- Telegram-терминал с 6 инлайн-кнопками (СТАРТ / СТОП / СТАТИСТИКА /
  ПОЗИЦИИ / PANIC SELL / ПОЧЕМУ МИМО?). Управление разрешено только одному
  `TELEGRAM_CHAT_ID` - любые сообщения от других пользователей отбрасываются.
- Все логи, комментарии и сообщения в Telegram на русском языке.

## Требования

- Python 3.11+
- Единственная зависимость: `aiohttp>=3.9`.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `BYBIT_API_KEY` | API ключ Bybit (V5 Unified Trading Account) |
| `BYBIT_API_SECRET` | Секрет Bybit |
| `TELEGRAM_TOKEN` | Токен Telegram-бота от @BotFather |
| `TELEGRAM_CHAT_ID` | Числовой chat_id владельца - единственный разрешённый |
| `GEMINI_API_KEY` | API ключ Google Gemini (generativelanguage.googleapis.com) |
| `NEWS_API_KEY` | API ключ https://newsapi.org |

Файл-образец: `.env.example`. Скопируйте его в `.env` и заполните.

## Установка и запуск

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# отредактируйте .env и проставьте реальные ключи
python main.py
```

По умолчанию используется testnet Bybit (`IS_TESTNET = True` в `config.py`).
Переключение в mainnet - осознанное действие: только после полной обкатки.

## Структура

```
config.py        # переменные окружения и константы (SYMBOL, риски, URL)
api_engine.py    # асинхронный Bybit V5 (aiohttp + HMAC-SHA256)
strategy.py      # индикаторы EMA/RSI/ATR и правила входа
news_engine.py   # заголовки NewsAPI
memory.py        # SQLite-хранилище сделок и отклонений (trades.db)
ai_analyst.py    # Gemini 2.0 Flash в роли финального фильтра
telegram_bot.py  # long-polling Telegram-терминал
main.py          # единая точка входа (asyncio.gather)
```

## Дисклеймер

Проект предназначен для обкатки на Bybit Testnet и образовательных целей.
Любая автоматическая торговля реальными средствами несёт риск полной
потери капитала. Автор не несёт ответственности за финансовые убытки.
Перед запуском в mainnet обязательно пройдите длительное тестирование и
убедитесь в корректности расчёта рисков и сигналов.
