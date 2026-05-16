# Price Monitor Bot

Telegram-бот для мониторинга цен на маркетплейсах Wildberries и Ozon.
Автоматически отслеживает скидки, генерирует посты с помощью AI и публикует в каналы.

## Возможности

- Парсинг цен WB и Ozon через API
- AI-генерация постов для канала (OpenAI/Groq)
- Антифрод-детектор завышенных скидок
- VIP-подписка с приоритетной публикацией (0 сек vs 30 мин)
- Персональные алерты по ключевым словам/цене
- Мониторинг конкурентов (продавцов)
- Реферальная система
- Партнерские ссылки (affiliate)

## Архитектура

```
09_price_monitor_bot/
├── bot/
│   ├── main.py             # Точка входа
│   ├── config.py           # Pydantic Settings конфиг
│   ├── db/
│   │   ├── models.py       # Схема БД (SQLite)
│   │   └── queries.py      # CRUD-функции
│   ├── parsers/
│   │   ├── wildberries.py  # Парсер WB
│   │   └── ozon.py         # Парсер Ozon
│   ├── ai/
│   │   ├── post_generator.py   # Генерация постов
│   │   ├── antifraud.py        # Детектор фейковых скидок
│   │   ├── ranker.py           # Ранжирование товаров
│   │   └── reviews_summary.py  # Саммари отзывов
│   ├── publisher/
│   │   ├── channel_publisher.py  # Публикация в каналы
│   │   ├── alert_sender.py      # Отправка алертов
│   │   └── affiliate.py         # Генерация партнерских ссылок
│   ├── handlers/
│   │   ├── start.py         # /start и онбординг
│   │   ├── alerts.py        # Управление алертами
│   │   ├── subscription.py  # VIP-подписка
│   │   ├── seller.py        # Мониторинг продавцов
│   │   └── referral.py      # Реферальная система
│   ├── scheduler/
│   │   └── tasks.py         # Периодические задачи
│   └── ui/
│       └── cards.py         # HTML-карточки для Telegram
├── requirements.txt
├── .env.example
└── README.md
```

## Установка

```bash
# 1. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Скопируйте и заполните конфиг
cp .env.example .env
# Отредактируйте .env, укажите токены

# 4. Запустите бота
python -m bot.main
```

## Переменные окружения

| Переменная | Описание | Обязательная |
|---|---|---|
| `TELEGRAM_TOKEN` | Токен Telegram-бота от @BotFather | Да |
| `TELEGRAM_CHANNEL_ID` | ID основного канала для публикаций | Да |
| `TELEGRAM_VIP_CHANNEL_ID` | ID VIP-канала | Да |
| `OPENAI_API_KEY` | Ключ API OpenAI/Groq | Да |
| `OPENAI_BASE_URL` | URL API (по умолчанию OpenAI) | Нет |
| `WB_API_TOKEN` | Токен API Wildberries | Да |
| `OZON_CLIENT_ID` | Client ID Ozon | Да |
| `OZON_API_KEY` | API Key Ozon | Да |
| `AFFILIATE_TAG` | Партнерский тег для ссылок | Нет |
| `DB_PATH` | Путь к файлу SQLite (по умолчанию `data/bot.db`) | Нет |
| `GROQ_API_KEY` | Ключ API Groq | Нет |

## Стек технологий

- **Python 3.11+**
- **aiogram 3.x** - Telegram Bot API
- **aiosqlite** - асинхронный SQLite
- **httpx** - HTTP-клиент
- **APScheduler** - планировщик задач
- **pydantic-settings** - конфигурация
- **openai** - генерация текста (совместимый API)
