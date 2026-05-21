# Crypto Exchanger Bot

Telegram-бот для обмена криптовалют (white-label) с использованием ChangeNOW API и Exolix в качестве резервного провайдера.

## Возможности

- Обмен 900+ криптовалют
- Два режима: плавающий курс и фиксированный курс
- Автоматический фоллбэк между провайдерами (ChangeNOW -> Exolix)
- Админ-панель со статистикой и мониторингом
- Автоматический опрос статусов обменов
- Кэширование курсов с настраиваемым TTL
- Наценка (markup) на все обмены
- Уведомления пользователей об изменении статуса
- Оповещения админа о зависших обменах

## Архитектура

```
09_crypto_exchanger/
  bot/
    handlers/       - Обработчики команд и FSM
    card_builder.py - Генерация карточек сообщений
    keyboards.py    - Inline-клавиатуры
    states.py       - FSM-состояния
  services/
    changenow.py    - Клиент ChangeNOW API v2
    exolix.py       - Клиент Exolix API
    exchange_router.py - Фасад с фоллбэком и наценкой
    rate_cache.py   - TTL-кэш курсов
    status_poller.py - Фоновый опрос статусов
  db/
    models.py       - Схема БД (SQLite)
    repository.py   - CRUD-операции
  config.py         - Конфигурация из .env
  main.py           - Точка входа
```

## Установка

### Docker (рекомендуется)

```bash
cp .env.example .env
# Заполните .env своими ключами
docker-compose up -d
```

### Ручная установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполните .env своими ключами
python main.py
```

## Конфигурация (.env)

| Переменная | Описание | По умолчанию |
|---|---|---|
| TELEGRAM_BOT_TOKEN | Токен бота от @BotFather | - |
| CHANGENOW_API_KEY | API-ключ ChangeNOW | - |
| EXOLIX_API_KEY | API-ключ Exolix | - |
| ADMIN_CHAT_ID | Telegram ID администратора | - |
| MARKUP_PERCENT | Наценка на обмены (%) | 1.5 |
| EXCHANGE_TIMEOUT_MINUTES | Таймаут зависших обменов (мин) | 60 |
| RATE_CACHE_TTL | TTL кэша курсов (сек) | 30 |
| STATUS_POLL_INTERVAL | Интервал опроса статусов (сек) | 30 |

## Команды бота

- `/start` - Приветствие и информация
- `/exchange` - Начать обмен
- `/status` - Проверить активные обмены
- `/help` - Справка
- `/admin` - Админ-панель (только для ADMIN_CHAT_ID)

## Поддерживаемые валюты

Бот поддерживает все валюты, доступные через ChangeNOW и Exolix (900+), включая:
BTC, ETH, USDT, BNB, SOL, XRP, ADA, DOGE, TRX, LTC, MATIC, AVAX, DOT, LINK, ATOM и др.
