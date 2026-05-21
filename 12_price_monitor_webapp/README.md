# Price Monitor WebApp

Полноценное веб-приложение для мониторинга цен на товары маркетплейсов.
Включает Telegram Mini App, админ-панель, расширенный бэкенд с AI-функциями и инфраструктурный слой.

## Архитектура

```
12_price_monitor_webapp/
├── backend/                    # FastAPI бэкенд
│   ├── app/
│   │   ├── config.py           # Конфигурация (pydantic-settings)
│   │   ├── main.py             # Точка входа приложения
│   │   ├── db/
│   │   │   ├── models.py       # SQLAlchemy модели
│   │   │   ├── session.py      # Подключение к БД
│   │   │   └── redis_client.py # Redis клиент
│   │   ├── middleware/
│   │   │   ├── auth.py         # JWT аутентификация
│   │   │   └── rate_limit.py   # Rate limiting
│   │   ├── routers/            # API-эндпоинты
│   │   │   ├── deals.py
│   │   │   ├── categories.py
│   │   │   ├── alerts.py
│   │   │   ├── favorites.py
│   │   │   ├── profile.py
│   │   │   ├── payments.py
│   │   │   ├── tracking.py
│   │   │   ├── chatbot.py
│   │   │   ├── arbitrage.py
│   │   │   ├── admin.py
│   │   │   ├── content.py
│   │   │   └── partners.py
│   │   ├── schemas/            # Pydantic v2 схемы
│   │   ├── services/           # Бизнес-логика и AI-сервисы
│   │   └── workers/            # Фоновые задачи (arq)
│   └── requirements.txt
├── frontend/                   # Telegram Mini App + Landing
│   ├── src/
│   │   ├── api/                # HTTP-клиент
│   │   ├── components/         # React компоненты
│   │   ├── hooks/              # useTelegram, useApi, useTheme
│   │   └── pages/              # Feed, ProductDetail, Alerts, Chat...
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── admin/                      # Админ-панель
│   ├── src/
│   │   ├── components/         # StatCard, Chart, DataTable
│   │   └── pages/              # Dashboard, Products, Users, Analytics...
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── infra/                      # Инфраструктура
│   ├── docker-compose.yml      # PostgreSQL, Redis, Nginx, сервисы
│   ├── init.sql                # Миграция базы данных
│   └── nginx.conf              # Reverse proxy конфигурация
└── README.md                   # Этот файл
```

## Стек технологий

| Слой | Технологии |
|------|-----------|
| Backend | Python 3.9+, FastAPI, SQLAlchemy 2 (async), asyncpg, Pydantic v2, arq, Redis |
| Frontend | TypeScript, React 18, Vite 5, Tailwind CSS, @twa-dev/sdk, Chart.js, React Query |
| Admin | TypeScript, React 18, Vite 5, Tailwind CSS, Chart.js, React Router |
| Infra | Docker Compose, PostgreSQL 16, Redis 7, Nginx |
| AI | OpenAI API (чат-бот, прогнозы цен, детекция ниш, модерация отзывов) |
| Платежи | ЮKassa |

## Быстрый старт

### 1. Поднять инфраструктуру

```bash
cd infra
docker-compose up -d postgres redis
```

Дождитесь готовности сервисов (healthcheck). PostgreSQL будет доступен на `localhost:5432`, Redis на `localhost:6379`.

### 2. Запустить бэкенд

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Создать .env файл (см. раздел "Переменные окружения")
cp .env.example .env

# Запуск
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API будет доступно на `http://localhost:8000`. Документация Swagger: `http://localhost:8000/docs`.

### 3. Запустить фронтенд (Telegram Mini App)

```bash
cd frontend
npm install
npm run dev
```

Приложение запустится на `http://localhost:5173`.

### 4. Запустить админ-панель

```bash
cd admin
npm install
npm run dev
```

Админ-панель запустится на `http://localhost:5174`.

## API Endpoints

| Группа | Префикс | Описание |
|--------|---------|----------|
| Deals | `/deals` | Лента скидок, поиск товаров, детали |
| Categories | `/categories` | Категории товаров |
| Alerts | `/alerts` | Управление уведомлениями о ценах |
| Favorites | `/favorites` | Избранные товары |
| Profile | `/profile` | Профиль пользователя, подписки |
| Payments | `/payments` | Оплата через ЮKassa, вебхуки |
| Tracking | `/tracking` | Отслеживание цен на товары |
| Chatbot | `/chatbot` | AI чат-бот для поиска товаров |
| Arbitrage | `/arbitrage` | Арбитраж цен между маркетплейсами |
| Admin | `/admin` | Управление платформой (только для админов) |
| Content | `/content` | Генерация контента, SEO-описания |
| Partners | `/partners` | Партнерская программа |

## Настройка Telegram Mini App

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Создайте бота: `/newbot` и сохраните токен.
3. Включите Mini App: `/mybots` -> выберите бота -> Bot Settings -> Menu Button -> Configure.
4. Задайте URL: укажите адрес, на котором размещен фронтенд (например, `https://your-domain.com`).
5. Для разработки используйте [ngrok](https://ngrok.com/) или аналог для проброса локального порта:
   ```bash
   ngrok http 5173
   ```
6. Пропишите полученный URL в настройках Menu Button у бота.
7. В файле `frontend/.env` установите:
   ```
   VITE_API_BASE_URL=https://your-backend-domain.com
   ```
8. Для валидации `initData` от Telegram используется `secret_key` и `telegram_bot_token` на бэкенде.

## Переменные окружения

### Backend (.env)

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `DATABASE_URL` | SQLite URI для локальной разработки | `sqlite+aiosqlite:///./data/api.db` |
| `POSTGRESQL_URL` | PostgreSQL URI для продакшена | `postgresql+asyncpg://price_monitor:price_monitor_secret@localhost:5432/price_monitor` |
| `REDIS_URL` | Redis URI | `redis://localhost:6379/0` |
| `SECRET_KEY` | Секрет для JWT подписи | `change-me-in-production` |
| `JWT_ALGORITHM` | Алгоритм JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Время жизни токена (минуты) | `1440` |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - |
| `TELEGRAM_ADMIN_ID` | Telegram ID администратора | `0` |
| `OPENAI_API_KEY` | Ключ OpenAI API | - |
| `OPENAI_BASE_URL` | Base URL для OpenAI-совместимого API | `https://api.openai.com/v1` |
| `YUKASSA_SHOP_ID` | ID магазина ЮKassa | - |
| `YUKASSA_SECRET_KEY` | Секретный ключ ЮKassa | - |
| `YUKASSA_WEBHOOK_SECRET` | Секрет для вебхуков ЮKassa | - |
| `SENTRY_DSN` | DSN для Sentry мониторинга | - |
| `ADMIN_TELEGRAM_IDS` | Список Telegram ID админов (через запятую) | - |
| `PROXY_LIST_FILE` | Путь к файлу со списком прокси | - |
| `FCM_SERVER_KEY` | Ключ Firebase Cloud Messaging | - |
| `PARTNER_COMMISSION_PERCENT` | Процент комиссии партнеров | `5.0` |

### Frontend (.env)

| Переменная | Описание |
|------------|----------|
| `VITE_API_BASE_URL` | URL бэкенд-API |

## Деплой

### Docker Compose (полный стек)

```bash
cd infra
docker-compose up -d
```

Это поднимет все сервисы:
- **PostgreSQL** - порт 5432
- **Redis** - порт 6379
- **Backend** - порт 8000
- **Frontend** - порт 3000
- **Admin** - порт 3001
- **Nginx** - порты 80/443 (reverse proxy)

### Продакшен-рекомендации

1. Замените все значения по умолчанию в `.env` на безопасные (особенно `SECRET_KEY`).
2. Настройте SSL-сертификаты в Nginx (Let's Encrypt).
3. Включите Sentry для мониторинга ошибок.
4. Настройте бэкапы PostgreSQL (pg_dump по расписанию).
5. Используйте отдельный Redis для кэша и очередей.
6. Для масштабирования запускайте несколько экземпляров бэкенда за Nginx.

### Сборка фронтенда для продакшена

```bash
# Telegram Mini App
cd frontend
npm run build    # результат в dist/

# Админ-панель
cd admin
npm run build    # результат в dist/
```

Собранные файлы из `dist/` раздаются через Nginx или любой статический хостинг.
