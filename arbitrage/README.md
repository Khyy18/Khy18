# Arbitrage Bot - AI-Powered Sports Betting Arbitrage System

**Полностью автоматизированная система арбитражных ставок на спорт с 11 AI-слоями, 5 стратегиями и продвинутой аналитикой.**

Бот сканирует коэффициенты десятков букмекеров в реальном времени, находит арбитражные возможности, фильтрует их через каскад AI-моделей, оптимально распределяет банкролл и размещает ставки с минимальным риском блокировки аккаунтов.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES (Источники данных)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │ The Odds  │  │ Pinnacle  │  │ Betfair  │  │ Betfair   │  │  Scraper  │ │
│  │ API       │  │ API       │  │ REST API │  │ Stream WS │  │ (bet365,  │ │
│  │(50+ BKs)  │  │(sharp line)│  │(exchange)│  │(real-time)│  │  Unibet)  │ │
│  └─────┬─────┘  └─────┬─────┘  └────┬─────┘  └─────┬─────┘  └─────┬─────┘ │
└────────┼───────────────┼────────────┼──────────────┼──────────────┼─────────┘
         │               │            │              │              │
         ▼               ▼            ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRATEGIES (5 стратегий)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Surebets  │  │ Value Bets│  │  Middles  │  │   Steam   │  │  Cash-Out │ │
│  │(гарант.   │  │(+EV vs    │  │(коридоры  │  │   Moves   │  │(досрочное │ │
│  │ прибыль)  │  │ sharp)    │  │ тоталов/  │  │(движение  │  │ закрытие) │ │
│  │           │  │           │  │ спредов)  │  │ линий)    │  │           │ │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘ │
└────────┼───────────────┼──────────────┼──────────────┼──────────────┼───────┘
         │               │              │              │              │
         ▼               ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AI PIPELINE (11 AI-слоев)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ai_filter │ │ai_alloc  │ │ai_anomaly│ │ ai_batch │ │ai_bk_cls │          │
│  │(оценка   │ │(Kelly +  │ │(детектор │ │(пакетная │ │(классиф. │          │
│  │ 0-100)   │ │ AI risk) │ │ аномалий)│ │ оценка)  │ │  БК)     │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ai_correl │ │ai_line_  │ │ai_news   │ │ai_optim  │ │ai_rate   │          │
│  │(корреляц.│ │predictor │ │_scanner  │ │(оптимиз. │ │_limiter  │          │
│  │ рынков)  │ │(прогноз  │ │(новости) │ │ портфеля)│ │(лимиты)  │          │
│  └──────────┘ │ линий)   │ └──────────┘ └──────────┘ └──────────┘          │
│               └──────────┘                                                   │
│  ┌──────────┐                                                                │
│  │ai_with-  │                                                                │
│  │drawal    │                                                                │
│  │(вывод)   │                                                                │
│  └──────────┘                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EXECUTION & MANAGEMENT                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Executor  │  │ Anti-Ban  │  │  Memory   │  │  Dedup    │  │ Telegram  │ │
│  │(parallel  │  │(задержки, │  │ (SQLite)  │  │(TTL 5min) │  │  Bot UI   │ │
│  │ legs)     │  │ лимиты)   │  │           │  │           │  │           │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │Settlement │  │CLV Tracker│  │Supervisor │  │  Ranker   │               │
│  │(Scores    │  │(отслежив. │  │(монитор   │  │(ранжиров.)│               │
│  │ API)      │  │ CLV)      │  │ здоровья) │  │           │               │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Стратегии (5)

| # | Стратегия | Модуль | Описание |
|---|-----------|--------|----------|
| 1 | **Surebets** | `scanner.py` | Гарантированная прибыль при ставках на все исходы у разных БК |
| 2 | **Value Bets** | `scanner.py` | Положительное мат. ожидание относительно sharp-линий Pinnacle |
| 3 | **Middles/Коридоры** | `middles.py` | Коридоры тоталов и спредов между разными БК (Poisson-модель) |
| 4 | **Steam Moves** | `steam_moves.py` | Обнаружение резких движений линий (steam) для раннего входа |
| 5 | **Cash-Out** | `cashout.py` | Досрочное закрытие позиций при движении линии в нашу сторону |

---

## AI-слои (11)

| # | Модуль | Назначение |
|---|--------|------------|
| 1 | `ai_filter.py` | LLM-оценка арбитража (0-100) с калибровкой по историческим данным |
| 2 | `ai_allocator.py` | Kelly-аллокация с AI-коррекцией рисков для каждой ноги |
| 3 | `ai_anomaly_detector.py` | Детектор аномальных коэффициентов (ловушки БК, ошибки данных) |
| 4 | `ai_batch.py` | Пакетная оценка нескольких арбитражей одним LLM-вызовом |
| 5 | `ai_bk_classifier.py` | Классификация букмекеров (sharp/soft/exchange) для приоритизации |
| 6 | `ai_correlation.py` | Анализ корреляций между рынками для хеджирования |
| 7 | `ai_line_predictor.py` | Прогноз движения линий (куда пойдет коэффициент) |
| 8 | `ai_news_scanner.py` | Мониторинг новостей (травмы, дисквалификации) для фильтрации |
| 9 | `ai_optimizer.py` | Оптимизация портфеля ставок (диверсификация по спортам/лигам) |
| 10 | `ai_rate_limiter.py` | Интеллектуальный rate limiter для AI-запросов (приоритеты) |
| 11 | `ai_withdrawal.py` | Стратегия вывода средств (когда, сколько, с какого БК) |

---

## Модули (полный список)

| Файл | Описание |
|------|----------|
| `__init__.py` | Инициализация пакета |
| `config.py` | Константы, переменные окружения, параметры |
| `main.py` | Точка входа, циклы сканирования и settlement |
| `odds_api.py` | Клиент The Odds API (коэффициенты, скоры, auto-discovery) |
| `pinnacle_api.py` | Клиент Pinnacle API (sharp-линии) |
| `betfair_api.py` | Клиент Betfair Exchange REST API (certlogin, ставки) |
| `betfair_stream.py` | WebSocket-стриминг Betfair (real-time цены) |
| `scraper.py` | Скраперы мягких БК (bet365, Unibet) - scaffold |
| `scanner.py` | Поиск surebets и value bets |
| `middles.py` | Поиск коридоров (middles) с Poisson-моделью |
| `steam_moves.py` | Обнаружение steam moves (резкие движения линий) |
| `cashout.py` | Стратегия досрочного закрытия позиций |
| `ai_filter.py` | LLM-оценка с калибровкой (ai_feedback) |
| `ai_allocator.py` | Kelly-аллокация с AI-коррекцией |
| `ai_anomaly_detector.py` | Детектор аномалий в коэффициентах |
| `ai_batch.py` | Пакетная AI-оценка нескольких арбитражей |
| `ai_bk_classifier.py` | Классификация букмекеров (sharp/soft) |
| `ai_correlation.py` | Корреляционный анализ рынков |
| `ai_line_predictor.py` | Прогноз движения линий |
| `ai_news_scanner.py` | Мониторинг спортивных новостей |
| `ai_optimizer.py` | Оптимизация портфеля ставок |
| `ai_rate_limiter.py` | Rate limiter для AI-запросов |
| `ai_withdrawal.py` | Стратегия вывода средств |
| `executor.py` | Размещение ставок (parallel legs, Betfair) |
| `anti_ban.py` | Anti-ban эвристики (задержки, лимиты, шум) |
| `memory.py` | SQLite-хранилище (арбитражи, банкролл, feedback) |
| `dedup.py` | Дедупликация арбитражей (TTL 5 мин) |
| `recheck.py` | Smart recheck коэффициентов |
| `settlement.py` | Расчет ставок по реальным результатам (Scores API) |
| `clv_tracker.py` | Отслеживание Closing Line Value |
| `ranker.py` | Ранжирование арбитражей по приоритету |
| `supervisor.py` | Мониторинг здоровья системы |
| `telegram_bot.py` | Telegram-интерфейс с inline-клавиатурой |
| `retry.py` | Универсальный retry с exponential backoff |
| `logging_config.py` | Конфигурация логирования |
| `utils.py` | Вспомогательные функции |

---

## Установка

### Через pip

```bash
# Клонирование
git clone <repo-url>
cd arbitrage

# Установка зависимостей
pip install -r requirements.txt

# Копирование конфигурации
cp ../.env.example .env
# Заполнить .env своими ключами (см. раздел "Конфигурация")
```

### Через Docker

```bash
cd arbitrage

# Сборка образа
docker build -t arbitrage-bot .

# Запуск
docker run --env-file .env -v ./data:/app/data arbitrage-bot
```

### Через docker-compose

```bash
cd arbitrage

# Запуск
docker-compose up -d

# Логи
docker-compose logs -f arbitrage-bot

# Остановка
docker-compose down
```

---

## Конфигурация

### Переменные окружения

| Переменная | Описание | Обязательная | По умолчанию |
|---|---|---|---|
| `ODDS_API_KEY` | API-ключ The Odds API | Да | - |
| `TELEGRAM_TOKEN` | Токен Telegram бота (@BotFather) | Да | - |
| `TELEGRAM_CHAT_ID` | ID чата для управления ботом | Да | - |
| `GROQ_API_KEY` | API-ключ Groq (AI-фильтрация) | Да | - |
| `PINNACLE_USER` | Логин Pinnacle | Нет | - |
| `PINNACLE_PASSWORD` | Пароль Pinnacle | Нет | - |
| `BETFAIR_APP_KEY` | Application Key Betfair | Нет | - |
| `BETFAIR_SESSION_TOKEN` | Session Token Betfair | Нет | - |
| `BETFAIR_CERT_PATH` | Путь к SSL-сертификату Betfair | Нет | - |
| `BETFAIR_KEY_PATH` | Путь к SSL-ключу Betfair | Нет | - |
| `ARB_DRY_RUN` | Режим симуляции (true/false) | Нет | `true` |
| `ARB_DB_PATH` | Путь к SQLite базе | Нет | `arbitrage/arbitrage.db` |
| `GROQ_MODEL` | Модель Groq LLM | Нет | `llama-3.3-70b-versatile` |
| `ARB_BANKROLL` | Начальный банкролл | Нет | `1000.0` |

### Параметры стратегий (config.py)

| Параметр | Значение | Описание |
|---|---|---|
| `MIN_ARB_PROFIT` | 1.0% | Минимальная прибыль для surebets |
| `MIN_VALUE_EDGE` | 3.0% | Минимальный edge для value bets |
| `MAX_BET_PCT` | 5.0% | Максимальная ставка (% от банкролла) |
| `SCAN_INTERVAL_SEC` | 30 сек | Интервал сканирования |
| `MAX_BANKROLL_EXPOSURE` | 20.0% | Максимальная экспозиция |
| `RECHECK_MIN_PROFIT_PCT` | 2.0% | Минимальный профит для recheck |
| `RECHECK_MAX_STALENESS_SEC` | 10 сек | Свежесть данных для recheck |

### Пример .env

```env
# === ОБЯЗАТЕЛЬНЫЕ ===
ODDS_API_KEY=your_odds_api_key_here
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
GROQ_API_KEY=gsk_your_groq_key_here

# === ОПЦИОНАЛЬНЫЕ ===
# Pinnacle (sharp-линии напрямую)
PINNACLE_USER=your_pinnacle_login
PINNACLE_PASSWORD=your_pinnacle_password

# Betfair Exchange
BETFAIR_APP_KEY=your_betfair_app_key
BETFAIR_SESSION_TOKEN=your_session_token
BETFAIR_CERT_PATH=/path/to/betfair.crt
BETFAIR_KEY_PATH=/path/to/betfair.key

# Режим работы
ARB_DRY_RUN=true
ARB_DB_PATH=arbitrage/arbitrage.db
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## Запуск

### Dev-режим (локально)

```bash
# Установка зависимостей
pip install -r arbitrage/requirements.txt

# Запуск в DRY_RUN
ARB_DRY_RUN=true python3.11 -m arbitrage.main
```

### Docker

```bash
cd arbitrage
docker build -t arbitrage-bot .
docker run -d \
  --name arbitrage \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart always \
  arbitrage-bot
```

### VPS (production)

```bash
# 1. Подготовка сервера (Ubuntu 22.04+)
apt update && apt install -y python3.11 python3.11-pip

# 2. Клонирование и установка
git clone <repo-url> /opt/arbitrage
cd /opt/arbitrage
pip install -r arbitrage/requirements.txt

# 3. Настройка systemd
cat > /etc/systemd/system/arbitrage-bot.service << 'EOF'
[Unit]
Description=Arbitrage Bot
After=network.target

[Service]
Type=simple
User=arbitrage
WorkingDirectory=/opt/arbitrage
EnvironmentFile=/opt/arbitrage/.env
ExecStart=/usr/bin/python3.11 -m arbitrage.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 4. Запуск
systemctl enable arbitrage-bot
systemctl start arbitrage-bot

# 5. Мониторинг
journalctl -u arbitrage-bot -f
```

---

## Получение API-ключей

### The Odds API

1. Регистрация на [the-odds-api.com](https://the-odds-api.com)
2. Бесплатный план: 500 запросов/месяц
3. Рекомендуемый план: Starter ($20/мес) - 5000 запросов
4. Ключ в разделе Dashboard -> API Key

### Betfair Exchange

1. Регистрация на [betfair.com](https://www.betfair.com)
2. Получение Application Key: My Account -> Developer App Keys
3. Для certlogin: создать SSL-сертификат в Account -> Security
4. Premium API (для стриминга): запрос через support

### Telegram Bot

1. Открыть [@BotFather](https://t.me/BotFather) в Telegram
2. Команда `/newbot`, выбрать имя
3. Скопировать токен
4. Для CHAT_ID: отправить боту сообщение, затем вызвать `https://api.telegram.org/bot<TOKEN>/getUpdates`

### Groq (AI)

1. Регистрация на [console.groq.com](https://console.groq.com)
2. Бесплатный план: 30 запросов/мин
3. Создать API Key в Settings -> API Keys
4. Рекомендуемая модель: `llama-3.3-70b-versatile`

---

## Тестирование

```bash
# Все тесты
python3.11 -m pytest tests/ -v

# Проверка импортов
python3.11 -c "import arbitrage"

# Проверка конкретных модулей
python3.11 -c "from arbitrage.middles import MiddleScanner, poisson_pmf, LEAGUE_AVERAGES"
python3.11 -c "from arbitrage.scraper import BookmakerScraper, Bet365Scraper"
python3.11 -c "from arbitrage.betfair_api import BetfairClient"
python3.11 -c "from arbitrage.executor import BetExecutor"
```

---

## Виды спорта

| Ключ | Лига | Ср. тотал |
|------|------|-----------|
| `soccer_epl` | Английская Премьер-лига | 2.7 |
| `soccer_spain_la_liga` | Испанская Ла Лига | 2.5 |
| `soccer_germany_bundesliga` | Немецкая Бундеслига | 3.0 |
| `soccer_italy_serie_a` | Итальянская Серия А | 2.4 |
| `soccer_france_ligue_one` | Французская Лига 1 | 2.5 |
| `soccer_uefa_champs_league` | Лига Чемпионов UEFA | 2.8 |
| `basketball_nba` | NBA | 220.5 |
| `basketball_euroleague` | Евролига | 155.0 |
| `tennis_atp_french_open` | Теннис ATP French Open | - |

При запуске бот выполняет auto-discovery: запрашивает `/v4/sports` для актуального списка.

---

## Disclaimer (Отказ от ответственности)

**ВНИМАНИЕ:** Данное программное обеспечение предоставляется исключительно в образовательных и исследовательских целях.

- Азартные игры связаны с риском полной потери денежных средств
- Букмекеры активно борются с арбитражерами и могут заблокировать аккаунты
- Авторы не несут ответственности за финансовые потери любого рода
- Использование бота в live-режиме осуществляется на ваш собственный риск
- Проверьте законодательство вашей юрисдикции относительно спортивных ставок
- Прошлые результаты не гарантируют будущую прибыль
- Бот работает в режиме DRY_RUN по умолчанию - переключение в live требует осознанного решения

---

## Лицензия

Проект создан в образовательных целях. Коммерческое использование без согласования запрещено.
