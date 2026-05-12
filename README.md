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
| `GROQ_API_KEY` | API ключ Groq (console.groq.com) для ИИ-модулей |
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
ai_groq.py             # общий Groq-клиент (OpenAI-совместимый endpoint)
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

## v2: Multi-strategy framework

Экспериментальная ветка `feat/v2-meanrevert` расширяет v2-ядро до
диспетчера двух подсистем, переключаемых по режиму рынка.

- 7 торговых символов: `BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT,
  DOGEUSDT, AVAXUSDT` (per-symbol `MIN_ATR_PCT` от 0.3% до 0.8% под
  реальную волатильность каждого актива).
- Две подсистемы, выбираемые детерминированным диспетчером по режиму
  символа (`sym_state.regime`):
    * `strategy_v2` - Donchian breakout на 1h с трендовым фильтром
      EMA200/1d + EMA50/4h, запускается только в режиме `TRENDING`.
    * `strategy_v2_meanrevert` - Bollinger Bands(20, 2σ) mean-reversion
      на 15m с фильтрами RSI(14) и ADX(14)<25, запускается только в
      режиме `RANGING`.
    * В режиме `CRISIS / UNKNOWN` обе подсистемы молчат (fail-CLOSED).
- Классификатор режима `ai_regime` теперь вызывается раз в 30 минут
  (`AI_REGIME_TTL_SEC = 30 * 60`) вместо раз в час - диспетчер быстрее
  замечает переход `TRENDING <-> RANGING`.
- Лимит совокупного открытого риска поднят до `GLOBAL_RISK_CAP = 4%`
  эквити: 7 символов и 2 подсистемы требуют больше headroom, чем
  прежние 3 символа / 1 подсистема.
- Риск на сделку mean-reversion = `RISK_PER_TRADE * 0.5` (сделок
  ожидается больше, R короче; половинный риск компенсирует частоту).

**Тестирование ограниченное, использовать с осторожностью.** Перед
переключением в реальную торговлю обязательно прогнать не менее суток
в `DRY_RUN=true`, убедиться что `[AI] regime` стабильно отдаёт разумные
классификации (не застревает в CRISIS), и только после этого ставить
`DRY_RUN=false`. Ветка не покрыта бэктестом - сбор статистики в проде
первые сутки в DRY_RUN это обязательный шаг, не рекомендация.

## v3: AI-veto gate (экспериментально)

v3 добавляет **финальный страховочный слой** между стратегией и ордером.
После того как strategy_v2/strategy_v2_meanrevert и все детерминистические
фильтры сказали «открываем», бот отправляет в Groq один узкий вопрос:
есть ли в свежих новостях по символу явный red-flag, из-за которого эту
сделку лучше пропустить? По умолчанию gate отвечает `approve`; veto
ставит только на явные события: hack биржи, депег стейблкоина, rug pull,
активное расследование SEC, major delisting, банкротство биржи,
критический баг смарт-контракта.

Gate **не генерирует** свои сигналы - только подтверждает или вето
существующий. Торговое решение остаётся за детерминистической стратегией.

### Режимы (переменная `AI_TRADE_GATE_MODE` в `.env`)

| Значение  | Поведение                                                    |
|-----------|--------------------------------------------------------------|
| `off`     | gate выключен полностью, Groq не вызывается                  |
| `shadow`  | gate вызывается и логируется, но **не влияет** на сделку     |
| `active`  | veto блокирует сделку с записью в `rejected_checks`          |

По умолчанию `shadow` - безопасный режим: можно увидеть в логах и в
Telegram-push, какие сделки gate хотел бы заблокировать, и сравнить их
исходы с реально открытыми. После того как вы убедились, что gate
блокирует именно то, что нужно - переключайте в `active`.

### Политика отказоустойчивости: fail-CLOSED

На любой ошибке (сеть, таймаут, невалидный JSON от модели, пустой ответ)
gate возвращает `verdict=error`. В `active`-режиме это трактуется как
veto: сделка **не открывается**. Логика: если мы не можем убедиться, что
новостной фон чист, безопаснее пропустить вход и дождаться следующего
сигнала.

В `shadow`-режиме `error` только логируется - на торговлю не влияет.

### Три источника данных для AI

1. Свежие заголовки по символу из NewsAPI за 6 часов (до 10 штук).
2. Текущий режим рынка и статус macro-sentinel blackout.
3. Параметры сделки: стратегия, сторона, цена входа, ATR(1h).

### Как переключить в `active`

На сервере:

```bash
sudo -u zenith sed -i 's/^AI_TRADE_GATE_MODE=.*/AI_TRADE_GATE_MODE=active/' /opt/zenith/.env
sudo systemctl restart zenith
```

Флаг читается через `os.getenv` на старте процесса - без перезапуска
сервиса значение не применится.

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
