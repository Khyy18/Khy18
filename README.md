# Zenith-Control Ultimate

Гибридная асинхронная криптоторговая система на Python 3.11. Работает на
бирже Bybit (V5 Unified Trading Account), управляется Telegram-терминалом,
принимает решения с помощью Google Gemini и использует новостной контекст
от NewsAPI. Память сделок ведётся в SQLite.

## Обновление v2 (overhaul)

v2 переписала торговое ядро целиком. Ключевые изменения:

- Детерминированная стратегия `strategy_v2` (мультитаймфреймовый Donchian
  с трендовым фильтром EMA200/1d + EMA50/4h + ATR-минимум + ADX на шортах).
  Никакого ИИ-гейта на входе.
- Трио ИИ-модулей подмешивается только к рискам:
    * `ai_macro_sentinel` раз в час решает про blackout перед крупными
      макрорелизами (fail-OPEN, кэш 55 минут).
    * `ai_regime` раз в 4 часа классифицирует режим `TRENDING / RANGING /
      CRISIS` на каждый символ (fail-CLOSED в CRISIS).
    * `ai_postmortem` раз в неделю (понедельник 00:00 UTC) отдаёт связный
      отчёт в Telegram.
- Мультисимвольный портфель: `SYMBOLS = [BTCUSDT, ETHUSDT, SOLUSDT]`,
  не более одной позиции на символ, суммарный открытый риск ограничен
  `GLOBAL_RISK_CAP = 3%` от стартового эквити.
- Ярусные kill-switches:
    * DAILY (`MAX_DAILY_LOSS = 3%`): пауза до UTC-полуночи.
    * WEEKLY (`MAX_WEEKLY_LOSS = 7%`): пауза на 7 дней от триггера.
    * MDD (`MAX_DRAWDOWN = 15%` от HWM): снятие только вручную через
      Telegram-кнопку «СНЯТЬ MDD» или команду `/resume_kill_switch`.
- PostOnly-лимит вход с фоллбэком в Market IOC (`POST_ONLY_TIMEOUT_SEC =
  30`), биржевые фильтры `instruments_info` и `validate_and_round_qty`.
- Telegram-терминал расширен до 10 кнопок: к легаси-шестёрке (СТАРТ,
  СТОП, СТАТИСТИКА, ПОЗИЦИИ, PANIC SELL, ПОЧЕМУ МИМО?) добавлены
  ОТЧЁТ, РЕЖИМЫ, KILL-STATE и СНЯТЬ MDD.
- Кнопка «ПОЧЕМУ МИМО?» переориентирована на детерминированный
  кольцевой буфер отклонений (таблица `rejected_checks`) - больше не
  опрашивает старую ИИ-таблицу `rejected_signals`.
- Event-driven бэктестер `backtester/` с синтетическим ГСЧ, реальными
  Binance 1m CSV, PostOnly/IOC симуляцией, walk-forward оптимизатором и
  метриками (Sharpe, Sortino, MDD, profit factor, exposure).
- Deploy-kit `deploy/` для systemd и Docker Compose.

## Возможности

- Ручная HMAC-SHA256 подпись Bybit V5 (без pybit).
- Стратегия и индикаторы на чистом Python (EMA/RSI/ATR/ADX/Donchian),
  без pandas/numpy/scipy.
- Vol-targeting сайзинг на базе 30-дневной реализованной волатильности,
  поверх ATR-стопа (`ATR_STOP_MULT = 2.5`).
- Chandelier-трейлинг (`ATR_TRAIL_MULT = 3.0`) активируется после
  движения `>= 1 * ATR` в плюс.
- Таймстоп `TIME_STOP_HOURS = 48` для зависших в нуле сделок.
- Telegram-терминал закрыт строгой проверкой `_is_authorized`: чужие
  сообщения отбрасываются молча, на callback от чужих отвечаем
  «Доступ запрещён» без изменения состояния.
- Русскоязычные логи, сообщения, комментарии. Секреты - только через
  `os.getenv`, никаких значений по умолчанию.

## Требования

- Python 3.11+.
- Единственная зависимость: `aiohttp>=3.9`.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `BYBIT_API_KEY` | API ключ Bybit (V5 Unified Trading Account) |
| `BYBIT_API_SECRET` | Секрет Bybit |
| `TELEGRAM_TOKEN` | Токен Telegram-бота от @BotFather |
| `TELEGRAM_CHAT_ID` | Числовой chat_id владельца, единственный разрешённый |
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
python3.11 main.py
```

По умолчанию используется testnet Bybit (`IS_TESTNET = True` в `config.py`).
Переключение в mainnet - осознанное действие: только после полной обкатки.

Production-развёртывание описано в `deploy/README.md` (systemd и Docker).

## Бэктестер

Модуль `backtester/` работает полностью локально, без Bybit. Подойдёт для
smoke-тестов стратегий и walk-forward оптимизации.

```bash
python3.11 -m backtester.run --help
python3.11 -m backtester.run --synthetic --bars 5000 --symbol BTCUSDT --strategy strategy_v2
python3.11 -m backtester.run --symbol BTCUSDT --from 2023-01-01 --to 2024-12-31 --strategy strategy_v2
python3.11 -m backtester.walkforward --help
```

Первая команда печатает справку, вторая прогоняет 5000 синтетических
1m-баров и печатает ASCII-таблицу метрик, третья запускает бэктест по
реальным 1m Binance CSV за выбранный диапазон (кэш в `backtester/data/`).

## Структура

```
config.py              # секреты и константы (SYMBOLS, TIMEFRAMES, риски, URL)
api_engine.py          # асинхронный Bybit V5 (PostOnly/IOC, trading-stop, фильтры)
strategy.py            # shim: re-export strategy_v2
strategy_v1.py         # legacy RSI-cross (справочно, для сравнения в бэктестере)
strategy_v2.py         # Donchian + трендовый фильтр + vol-targeting
ai_gemini.py           # общий Gemini-клиент (x-goog-api-key заголовком)
ai_macro_sentinel.py   # blackout перед макрорелизами (часовой тикер)
ai_regime.py           # TRENDING/RANGING/CRISIS (4-часовой тикер на символ)
ai_postmortem.py       # еженедельный отчёт (понедельник 00:00 UTC)
ai_analyst.py          # остаточный модуль: explain_last_rejection
news_engine.py         # заголовки NewsAPI
memory.py              # SQLite: trades / rejected_checks / equity_curve
telegram_bot.py        # long-polling Telegram-терминал (10 кнопок)
main.py                # единая точка входа (asyncio.gather)
backtester/            # event-driven бэктестер + walk-forward
deploy/                # install.sh, systemd unit, Dockerfile, compose
```

## Поддерживаемые биржи

| Биржа | Статус | Файл адаптера |
|-------|--------|---------------|
| Bybit V5 | реализован | `exchanges/bybit.py` |
| (следующая) | в планах | - |

Переключение биржи: переменная окружения `EXCHANGE=bybit` в `.env`.

Архитектура: `exchanges/base.ExchangeAdapter` определяет единый интерфейс.
Добавление новой биржи = один файл + регистрация. Подробнее: `exchanges/README.md`.

## Изменения v2.1

- Исправлен MDD self-trip: снимок эквити использует `cumulative_pnl` (не сбрасываемый).
- PostOnly fill подтверждается через execution history (phantom-trade fix).
- Entry price берётся из реального fill, а не из limit_price.
- Exit price и PnL берутся из `/v5/position/closed-pnl` (fallback на 1m kline).
- Дедупликация rejection ring: якорь бара продвигается безусловно.
- SQLite временные фильтры через `datetime(ts)`.
- Бэктестер совместим со strategy_v1 (on_bar/on_fill/set_params заглушки).
- Введена абстракция `ExchangeAdapter` для замены биржи одним файлом.

## Дисклеймер

Проект предназначен для обкатки на Bybit Testnet и образовательных целей.
Любая автоматическая торговля реальными средствами несёт риск полной
потери капитала. Автор не несёт ответственности за финансовые убытки.
Перед запуском в mainnet обязательно пройдите длительное тестирование и
убедитесь в корректности расчёта рисков и сигналов.

## Легаси v1

Стратегия v1 доступна как `strategy_v1.py` для обратного сравнения и
остаётся прежним RSI-cross шаблоном (EMA(200) + RSI(14) + breakeven +
trailing TP). Бэктестер принимает её через флаг `--strategy strategy_v1`.
Из лайв-рантайма v2 она не вызывается.
