# ИИ-Психолог по видеосвязи - Telegram Mini App

## Описание

MVP-прототип Telegram Mini App для проведения видео-сессий с ИИ-психологом. Приложение позволяет пользователю начать видеозвонок с ИИ-аватаром, который выступает в роли психолога-консультанта, использующего методы когнитивно-поведенческой терапии (КПТ) и гештальт-подхода.

Основные возможности: авторизация через Telegram WebApp (initDataRaw + HMAC-SHA256 валидация), видеозвонок с ИИ-аватаром в реальном времени (STT -> LLM -> TTS -> Avatar), поминутная тарификация с автоматическим списанием баланса, пополнение через Telegram Stars и ЮKassa.

Проект представляет собой монорепозиторий с FastAPI-бэкендом (Python) и React-фронтендом (Vite + TailwindCSS), оптимизированным для работы внутри Telegram Mini App с использованием нативных CSS-переменных Telegram для темизации.

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                 Telegram Mini App                     │
│              (React + Vite + TailwindCSS)            │
└──────────────────────┬──────────────────────────────┘
                       │ WebSocket + REST API
                       ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                      │
├──────────┬───────────┬────────────┬─────────────────┤
│   Auth   │  Billing  │    Call    │    Models        │
│(Telegram)│ (Worker)  │(WebSocket) │  (SQLAlchemy)   │
└──────────┴─────┬─────┴─────┬──────┴─────────────────┘
                 │            │
                 ▼            ▼
┌────────────────────┐  ┌─────────────────────────────┐
│  Redis (fakeredis) │  │       AI Pipeline            │
│  Pubsub: billing   │  │  STT (Groq Whisper)         │
│  force_end signals  │  │  LLM (Claude/GPT-4o)       │
└────────────────────┘  │  TTS (ElevenLabs)           │
                        │  Avatar (Simli/LiveKit)      │
                        └─────────────────────────────┘
```

## Технологический стек

### Backend

- **Python 3.11+**
- **FastAPI** - асинхронный веб-фреймворк
- **SQLAlchemy 2.0** (async) - ORM с поддержкой asyncio
- **aiosqlite** - асинхронный драйвер SQLite для разработки
- **PyJWT** - создание и верификация JWT-токенов
- **fakeredis** - эмуляция Redis для разработки без внешних зависимостей
- **Pydantic Settings** - управление конфигурацией через переменные окружения
- **Uvicorn** - ASGI-сервер

### Frontend

- **React 18** - UI-библиотека
- **Vite 5** - сборщик и dev-сервер
- **TailwindCSS 3** - utility-first CSS-фреймворк
- **React Router 6** - клиентская маршрутизация
- **@telegram-apps/sdk-react** - Telegram Mini App SDK

### AI Pipeline (стабы для MVP)

- **STT**: Groq Whisper API
- **LLM**: Claude (Anthropic) / GPT-4o (OpenAI)
- **TTS**: ElevenLabs API
- **Avatar**: Simli / LiveKit

## Структура проекта

```
09_ai_psychologist_video/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, lifespan, CORS, роутеры
│   │   ├── config.py            # Pydantic Settings (переменные окружения)
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── telegram.py      # Валидация Telegram initDataRaw (HMAC-SHA256)
│   │   │   ├── jwt.py           # Создание/верификация JWT
│   │   │   └── router.py        # POST /auth/telegram
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── database.py      # SQLAlchemy модели (User, Session, Transaction)
│   │   ├── billing/
│   │   │   ├── __init__.py
│   │   │   ├── worker.py        # BillingWorker - поминутное списание
│   │   │   └── payment.py       # Стабы Stars/YooKassa + POST /billing/topup
│   │   ├── call/
│   │   │   ├── __init__.py
│   │   │   ├── websocket.py     # WS /ws/call/{session_id} - координатор звонка
│   │   │   └── pipeline.py      # AIPipeline - STT->LLM->TTS->Avatar стабы
│   │   └── prompts/
│   │       ├── __init__.py
│   │       └── psychologist.py  # Системный промпт психолога (КПТ + Гештальт)
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── main.jsx             # Точка входа React
│   │   ├── App.jsx              # Роутинг, TelegramProvider
│   │   ├── index.css            # Tailwind directives + Telegram CSS vars
│   │   ├── components/
│   │   │   ├── CallScreen.jsx   # Экран видеозвонка (fullscreen + PiP)
│   │   │   ├── Dashboard.jsx    # Главная: баланс, история, старт сессии
│   │   │   └── TopUp.jsx        # Пополнение баланса (Stars / YooKassa)
│   │   ├── hooks/
│   │   │   ├── useTelegramAuth.js  # Авторизация через Telegram SDK
│   │   │   └── useWebSocket.js     # WebSocket-подключение к серверу
│   │   └── utils/
│   │       └── api.js           # HTTP-клиент с JWT
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
└── README.md                    # (этот файл)
```

## Быстрый старт

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Сервер будет доступен по адресу `http://localhost:8000`. Документация API: `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev-сервер запустится на `http://localhost:5173`. Запросы к API проксируются на `localhost:8000`.

## Переменные окружения

Создайте файл `.env` в директории `backend/`:

```env
BOT_TOKEN=your_telegram_bot_token
JWT_SECRET=your_secret_key
DATABASE_URL=sqlite+aiosqlite:///./dev.db
REDIS_URL=redis://localhost:6379
RATE_PER_MINUTE=5.00
LLM_API_KEY=your_llm_api_key
STT_API_KEY=your_stt_api_key
TTS_API_KEY=your_tts_api_key
AVATAR_API_KEY=your_avatar_api_key
```

| Переменная | Описание | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | Токен Telegram-бота (из @BotFather) | - |
| `JWT_SECRET` | Секрет для подписи JWT-токенов | `dev-secret-change-me` |
| `DATABASE_URL` | URL базы данных (SQLAlchemy async) | `sqlite+aiosqlite:///./dev.db` |
| `REDIS_URL` | URL Redis-сервера | `redis://localhost:6379` |
| `RATE_PER_MINUTE` | Стоимость минуты сессии (руб.) | `5.00` |
| `LLM_API_KEY` | Ключ API для LLM (Claude/GPT-4o) | - |
| `STT_API_KEY` | Ключ API для STT (Groq Whisper) | - |
| `TTS_API_KEY` | Ключ API для TTS (ElevenLabs) | - |
| `AVATAR_API_KEY` | Ключ API для Avatar (Simli/LiveKit) | - |

## Режим разработки

Проект разработан так, чтобы запускаться локально без внешних зависимостей:

- **База данных**: используется `aiosqlite` - файловая SQLite БД, не требует установки PostgreSQL или другого СУБД. Файл `dev.db` создается автоматически при первом запуске.
- **Redis**: используется `fakeredis` - in-memory эмуляция Redis. Если реальный Redis недоступен, приложение автоматически переключается на fakeredis. Pubsub-каналы (billing, force_end) работают внутри процесса.
- **AI Pipeline**: все вызовы к внешним API (STT, LLM, TTS, Avatar) реализованы как стабы, возвращающие mock-ответы. Это позволяет тестировать весь флоу без реальных API-ключей.

## API Endpoints

### REST API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/health` | Проверка состояния сервера |
| `POST` | `/auth/telegram` | Авторизация через Telegram initDataRaw |
| `POST` | `/billing/topup` | Пополнение баланса пользователя |

### WebSocket

| Путь | Описание |
|---|---|
| `WS /ws/call/{session_id}` | Видеозвонок - координация сессии с ИИ-психологом |

#### POST /auth/telegram

Запрос:
```json
{
  "init_data_raw": "query_id=...&user=...&auth_date=...&hash=..."
}
```

Ответ:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "uuid",
    "telegram_id": 123456789,
    "username": "user",
    "first_name": "Name",
    "balance": "0.00"
  }
}
```

#### POST /billing/topup

Запрос:
```json
{
  "user_id": "uuid",
  "amount": 100.00,
  "source": "demo"
}
```

Ответ:
```json
{
  "success": true,
  "new_balance": "100.00",
  "transaction_id": "uuid"
}
```

#### WS /ws/call/{session_id}

Подключение: `ws://localhost:8000/ws/call/{session_id}?token=JWT_TOKEN`

Сообщения от клиента:
- Бинарные: аудио-чанки (PCM/WebM)
- JSON: `{"type": "mute"}`, `{"type": "unmute"}`, `{"type": "end_call"}`

Сообщения от сервера:
- JSON: `{"type": "status", "status": "listening|thinking|speaking"}`
- JSON: `{"type": "transcript", "text": "..."}` 
- JSON: `{"type": "force_end", "reason": "insufficient_balance"}`
- Бинарные: аудио-ответы TTS

## Лицензия / Disclaimer

**Это MVP-прототип, созданный в образовательных и демонстрационных целях.**

Данное приложение НЕ является заменой реальной психологической помощи. ИИ-психолог не может ставить диагнозы, назначать лечение или заменить квалифицированного специалиста.

Если вы или кто-то из ваших близких нуждается в помощи:
- Телефон доверия: **8-800-2000-122** (бесплатно, круглосуточно)
- Экстренная помощь: **112**
