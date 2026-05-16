# Price Monitor

Единая платформа для мониторинга цен на маркетплейсах Wildberries и Ozon. Автоматически отслеживает скидки, уведомляет пользователей через Telegram-бот и Mini App, предоставляет админ-панель для управления и мобильное приложение.

## Архитектура

Монорепозиторий объединяет все компоненты системы:

```
price_monitor/
├── backend/       # FastAPI REST API сервер
├── bot/           # Telegram бот (парсинг + публикация)
├── frontend/      # Telegram Mini App (React + Vite)
├── admin/         # Админ-панель (React + Vite)
├── mobile/        # Мобильное приложение (React Native)
├── infra/         # Docker-конфигурация инфраструктуры
└── docs/          # Документация (листинг, политика)
```

## Технологический стек

| Компонент | Технологии |
|-----------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy (async), Pydantic Settings, PostgreSQL, Redis |
| Bot | Python 3.11, aiogram 3, APScheduler, Groq AI, Pydantic Settings |
| Frontend | TypeScript, React 18, Vite, Tailwind CSS, Telegram Web App SDK |
| Admin | TypeScript, React 18, Vite, Tailwind CSS, Recharts |
| Mobile | TypeScript, React Native 0.73, React Navigation, React Query |
| Infra | Docker Compose, PostgreSQL, Redis, Nginx |

## Быстрый старт

### Предварительные требования

- Python 3.11+
- Node.js 18+
- Docker и Docker Compose (для инфраструктуры)

### 1. Настройка окружения

```bash
cp .env.example .env
# Заполните необходимые переменные в .env
```

### 2. Инфраструктура

```bash
make infra
```

Запускает PostgreSQL, Redis и Nginx через Docker Compose.

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
cd ..
make backend
```

API будет доступен по адресу `http://localhost:8000`.

### 4. Telegram бот

```bash
cd bot
pip install -r requirements.txt
cd ..
make bot
```

### 5. Frontend (Telegram Mini App)

```bash
cd frontend
npm install
cd ..
make frontend
```

### 6. Admin панель

```bash
cd admin
npm install
cd ..
make admin
```

### 7. Мобильное приложение

```bash
cd mobile
npm install
npx react-native run-android
```

### Запуск всех сервисов одной командой

```bash
make dev
```

Запускает backend, bot и frontend параллельно.

## Команды Makefile

| Команда | Описание |
|---------|----------|
| `make dev` | Запуск backend + bot + frontend параллельно |
| `make backend` | Запуск FastAPI сервера (порт 8000) |
| `make bot` | Запуск Telegram бота |
| `make frontend` | Запуск dev-сервера фронтенда |
| `make admin` | Запуск dev-сервера админ-панели |
| `make build` | Сборка frontend и admin для продакшена |
| `make infra` | Запуск инфраструктуры (PostgreSQL, Redis, Nginx) |

## Переменные окружения

Все переменные описаны в файле `.env.example`. Основные группы:

### Backend

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `DATABASE_URL` | URL базы данных (SQLite/PostgreSQL) | `sqlite+aiosqlite:///./data/api.db` |
| `POSTGRESQL_URL` | URL PostgreSQL | `postgresql+asyncpg://...` |
| `REDIS_URL` | URL Redis | `redis://localhost:6379/0` |
| `SECRET_KEY` | Секретный ключ для JWT | `change-me-in-production` |
| `JWT_ALGORITHM` | Алгоритм JWT | `HS256` |
| `JWT_EXPIRE_MINUTES` | Время жизни токена (мин) | `1440` |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - |
| `TELEGRAM_ADMIN_ID` | ID администратора | `0` |
| `OPENAI_API_KEY` | Ключ OpenAI API | - |
| `OPENAI_BASE_URL` | URL OpenAI-совместимого API | `https://api.openai.com/v1` |
| `YUKASSA_SHOP_ID` | ID магазина ЮKassa | - |
| `YUKASSA_SECRET_KEY` | Секретный ключ ЮKassa | - |
| `SENTRY_DSN` | DSN для Sentry | - |
| `FCM_SERVER_KEY` | Ключ Firebase Cloud Messaging | - |
| `PARTNER_COMMISSION_PERCENT` | Процент партнерской комиссии | `5.0` |

### Bot

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `TELEGRAM_TOKEN` | Токен бота | - |
| `TELEGRAM_CHANNEL_ID` | ID основного канала | `0` |
| `TELEGRAM_VIP_CHANNEL_ID` | ID VIP канала | `0` |
| `GROQ_API_KEY` | Ключ Groq API | - |
| `WB_API_TOKEN` | API токен Wildberries | - |
| `OZON_CLIENT_ID` | Client ID Ozon | - |
| `OZON_API_KEY` | API ключ Ozon | - |
| `AFFILIATE_TAG` | Тег партнерской программы | - |
| `DB_PATH` | Путь к БД бота | `data/bot.db` |
| `PARSE_INTERVAL_MINUTES` | Интервал парсинга (мин) | `30` |
| `API_BASE_URL` | URL бэкенда | `http://localhost:8000` |

### Frontend

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `VITE_API_BASE_URL` | URL API для фронтенда | `http://localhost:8000` |

## Структура компонентов

### Backend (`backend/`)

REST API на FastAPI с асинхронным SQLAlchemy. Обрабатывает авторизацию через Telegram, управление подписками, платежи через ЮKassa, парсинг товаров, push-уведомления.

### Bot (`bot/`)

Telegram бот на aiogram 3. Парсит товары с Wildberries и Ozon, генерирует описания через AI (Groq), публикует в каналы с задержкой для VIP/free подписчиков.

### Frontend (`frontend/`)

Telegram Mini App на React + Vite + Tailwind. Интерфейс для пользователей: просмотр товаров, управление подписками, партнерская программа.

### Admin (`admin/`)

Панель администратора на React + Vite + Tailwind + Recharts. Управление товарами, пользователями, аналитика, настройки парсеров.

### Mobile (`mobile/`)

Мобильное приложение на React Native 0.73 для Android. Повторяет функциональность Mini App с нативным UX. Поддерживает push-уведомления через FCM.

### Infra (`infra/`)

Docker Compose конфигурация: PostgreSQL, Redis, Nginx reverse proxy.

## Лицензия

Проприетарный проект. Все права защищены.
