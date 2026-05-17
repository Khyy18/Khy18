# AI-Astrolог: Твой личный разбор по видеосвязи

Telegram Mini App для живых астрологических консультаций с AI-персонажем.
Пользователь вводит дату/время/место рождения, получает натальную карту и начинает голосовой видеозвонок с AI-астрологом "Стеллой" -- харизматичной 22-летней девушкой-блогером, которая разбирает карту в режиме реального времени.

---

## Архитектура

```
+---------------------+           +---------------------------+
|   TMA Frontend      |           |     FastAPI Backend       |
|  (React + Vite)     |           |     (Python 3.11)        |
|                     |           |                           |
|  OnboardingScreen   +--REST---->+  /api/session/start       |
|  PaymentModal       |           |  /api/balance/topup       |
|  AstroCall UI       |           |  /api/geocode             |
|  WebRTC abstraction |           |  /api/payments/*          |
|                     |           |  /metrics                 |
|                     +--WS------>+  /ws/call/{id}            |
|                     +--WS------>+  /ws/billing/{id}         |
+---------------------+           +----------+----------------+
                                             |
                                             | async pipeline
                                             v
                                  +----------+----------+
                                  |     AI Pipeline     |
                                  |   (circuit breakers)|
                                  |                     |
                                  | 1. VAD (energy)     |
                                  | 2. Groq STT         |
                                  | 3. Claude LLM       |
                                  | 4. ElevenLabs TTS   |
                                  |    (streaming)      |
                                  | 5. Lip-Sync Avatar  |
                                  +---------------------+

+---------------------+           +---------------------+
|       Redis         |           |     PostgreSQL      |
|  - User balances    |           |  - Users            |
|  - Session state    |           |  - Sessions         |
|  - Billing pub/sub  |           |  - Billing log      |
|  - Rate limiting    |           |  (audit trail)      |
+---------------------+           +---------------------+
```

### Ключевые архитектурные решения

- **Redis pub/sub** для биллинга: billing worker публикует события в канал `billing:{session_id}`, WebSocket-хендлер подписывается и пересылает клиенту. Позволяет горизонтально масштабировать backend.
- **PostgreSQL** для персистентного хранения: пользователи, сессии, аудит-лог биллинговых событий. Используется asyncpg через SQLAlchemy async.
- **Circuit breakers** на внешних API (Groq, Anthropic, ElevenLabs): автоматическое отключение при каскадных ошибках, graceful degradation с fallback-ответами.
- **Graceful shutdown**: SIGTERM-хендлер прекращает прием новых сессий, ожидает завершения активных, затем корректно закрывает все соединения.
- **First-message auth** на WebSocket: вместо токена в query string, клиент отправляет `{"type": "auth", "token": "..."}` первым сообщением.

---

## Tech Stack

### Backend
| Технология | Назначение |
|---|---|
| Python 3.11 | Runtime |
| FastAPI | HTTP + WebSocket framework |
| Uvicorn | ASGI server |
| pyswisseph | Swiss Ephemeris для расчета натальной карты |
| Redis (async) | Балансы, сессии, pub/sub, rate limiting |
| PostgreSQL + asyncpg | Персистентное хранение, аудит |
| SQLAlchemy 2.0 (async) | ORM |
| Pydantic v2 | Валидация данных и настройки |
| httpx | Async HTTP клиент с connection pooling |
| tenacity | Retry-логика для circuit breakers |
| prometheus-client | Метрики |
| timezonefinder | Определение таймзоны по координатам |

### Frontend
| Технология | Назначение |
|---|---|
| React 18 | UI framework |
| TypeScript 5 | Type safety |
| Vite 6 | Build tool / dev server |
| TailwindCSS 3 | Utility-first CSS |
| @telegram-apps/sdk-react | Telegram Mini App SDK |

### External APIs
| Сервис | Роль |
|---|---|
| Groq (Distil-Whisper) | Speech-to-Text |
| Anthropic Claude | LLM для персонажа-астролога |
| ElevenLabs | Text-to-Speech (streaming) |
| Simli / LiveKit | Lip-sync avatar видео |
| Nominatim (OSM) | Геокодинг городов |
| Telegram Bot API | Платежи через Telegram Stars |

---

## Модули

### backend/app/astro.py -- Natal Chart
Расчет полной натальной карты через Swiss Ephemeris: позиции 10 планет, 12 домов (Плацидус), аспекты с орбисами.

### backend/app/prompts.py -- System Prompt Persona
Формирует системный промпт для Claude, определяющий персонажа "Стеллу". Натальная карта инжектится для персонализации.

### backend/app/billing.py -- Billing Manager
Поминутная тарификация через Redis. Lua-скрипт для атомарного check-and-deduct. Pub/sub для рассылки событий. LOW_BALANCE_WARNING перед исчерпанием.

### backend/app/session_store.py -- Redis Session Store
Хранение UserSession, conversation history, pipeline context, auth-токенов в Redis с TTL.

### backend/app/telegram_auth.py -- Telegram Auth
Валидация initData через HMAC-SHA256 по алгоритму Telegram. FastAPI dependency для защиты эндпоинтов.

### backend/app/circuit_breaker.py -- Circuit Breaker
Паттерн circuit breaker для внешних API. Состояния: closed/open/half-open. Exponential backoff через tenacity.

### backend/app/streaming_tts.py -- Streaming TTS
Потоковая генерация речи через ElevenLabs streaming API. Разбивает текст на предложения, стримит чанки.

### backend/app/vad.py -- Voice Activity Detection
Energy-based VAD для детекции речи. Определяет конец фразы по длительности тишины. Буферизация аудио.

### backend/app/geocoding.py -- Geocoding
Поиск города через Nominatim (OSM), определение координат и таймзоны через timezonefinder.

### backend/app/database.py -- PostgreSQL Database
SQLAlchemy async с моделями User, Session, BillingEventLog. Автоматическое создание таблиц при старте.

### backend/app/rate_limiter.py -- Rate Limiter
Sliding window rate limiter на Redis sorted sets. FastAPI dependency для защиты эндпоинтов от abuse.

### backend/app/metrics.py -- Prometheus Metrics
Кастомные метрики: active_calls, call_duration, billing_events, external_api_latency, external_api_errors.

### backend/app/payments.py -- Telegram Stars Payments
Интеграция с Telegram Stars: создание invoice, обработка webhook, пакеты (stars -> coins).

### backend/app/http_client.py -- Shared HTTP Client
Единый httpx.AsyncClient с connection pooling (100 connections, 30s timeout).

### frontend/src/components/OnboardingScreen.tsx -- Onboarding
Пошаговый ввод данных рождения: дата, время, город (с автокомплитом через /api/geocode). Telegram-стиль.

### frontend/src/components/PaymentModal.tsx -- Payment Modal
Модальное окно покупки монет через Telegram Stars. Пакеты на выбор.

### frontend/src/components/AstroCall.tsx -- Call UI
Полноэкранный видеозвонок: аватар, превью камеры, статус pipeline, кнопки управления, баланс.

---

## API Endpoints

### POST /api/session/start

Создает новую сессию: рассчитывает натальную карту, инициализирует AI pipeline.
Требует заголовок `X-Telegram-Init-Data` (валидация через HMAC-SHA256).

**Request:**
```json
{
  "user_id": "tg_12345",
  "birth_data": {
    "date": "1995-03-15",
    "time": "14:30",
    "lat": 55.7558,
    "lon": 37.6173,
    "city": "Москва",
    "tz_offset": 3.0
  },
  "balance": 100
}
```

**Response:**
```json
{
  "session_id": "uuid-string",
  "natal_chart": { "planets": {...}, "houses": {...}, "ascendant": "Gemini", "mc": "Pisces", "aspects": [...] },
  "balance": 100,
  "token": "session-auth-token-for-websocket"
}
```

### GET /api/session/{session_id}/status

Возвращает текущий статус сессии.

### POST /api/balance/topup

Пополнение баланса пользователя. Rate limited: 5 запросов в 60 секунд.

### GET /api/geocode?city={query}

Поиск города по названию. Возвращает список подсказок с координатами и таймзоной.

**Response:**
```json
{
  "suggestions": [
    {
      "display_name": "Москва, Россия",
      "lat": 55.7558,
      "lon": 37.6173,
      "timezone": "Europe/Moscow"
    }
  ]
}
```

### POST /api/payments/create-invoice

Создает invoice для оплаты через Telegram Stars.

**Request:**
```json
{
  "user_id": "tg_12345",
  "stars_amount": 100
}
```

**Response:**
```json
{
  "invoice_url": "https://t.me/$...",
  "stars_amount": 100,
  "coins_amount": 250
}
```

Доступные пакеты: 50 stars = 100 coins, 100 stars = 250 coins, 200 stars = 600 coins, 500 stars = 1800 coins.

### POST /api/payments/webhook

Обработка webhook от Telegram: pre_checkout_query (одобрение) и successful_payment (зачисление монет).

### GET /metrics

Prometheus-метрики в формате text/plain.

### GET /health

Health check. Возвращает `{"status": "shutting_down"}` при graceful shutdown.

---

## WebSocket Protocol

### WS /ws/call/{session_id}

Двунаправленный канал для обмена аудио/видео данными.

**Аутентификация (первое сообщение):**
```json
{"type": "auth", "token": "session-token-from-start-response"}
```

**Pipeline State Events (Server -> Client):**
```json
{"type": "pipeline_state", "state": "LISTENING"}
{"type": "pipeline_state", "state": "THINKING"}
{"type": "pipeline_state", "state": "SPEAKING"}
```

**Client -> Server:** Binary audio frames (WebM/Opus или 16-bit PCM)

**Server -> Client:** JSON response + binary audio
```json
{
  "type": "response",
  "transcript": "Расскажи про мою Луну",
  "response_text": "Ооо, у тебя Луна во Льве, это вообще огонь!",
  "has_audio": true,
  "has_video": false
}
```

После JSON, если `has_audio: true`, сервер отправляет binary frame с MP3/PCM аудио.

### WS /ws/billing/{session_id}

Канал для биллинговых уведомлений. Тоже требует first-message auth.

**Типы событий:**

| Event | Описание |
|---|---|
| `BALANCE_UPDATE` | Списание за интервал (amount, balance_after) |
| `LOW_BALANCE_WARNING` | Предупреждение: баланс скоро закончится |
| `TERMINATE_CALL` | Баланс исчерпан, завершить звонок |

```json
{
  "event_type": "LOW_BALANCE_WARNING",
  "user_id": "tg_12345",
  "session_id": "uuid-string",
  "amount": 0,
  "balance_after": 15,
  "timestamp": "2024-01-15T12:04:00"
}
```

---

## Frontend: Onboarding Flow

1. **OnboardingScreen** -- пользователь вводит дату и время рождения
2. **Город** -- автокомплит через `/api/geocode`, выбор из подсказок (координаты + timezone)
3. **Старт сессии** -- POST `/api/session/start`, получение токена
4. **AstroCall** -- подключение к WS с first-message auth, начало разговора
5. **PaymentModal** -- если баланс мал, покупка через Telegram Stars

---

## Environment Variables

Создайте файл `.env` в директории `backend/`:

| Переменная | Описание | Default |
|---|---|---|
| `REDIS_URL` | URL подключения к Redis | `redis://localhost:6379/0` |
| `DATABASE_URL` | PostgreSQL connection string | `""` (disabled) |
| `GROQ_API_KEY` | Groq API key (STT) | `""` |
| `ANTHROPIC_API_KEY` | Anthropic API key (LLM) | `""` |
| `ELEVENLABS_API_KEY` | ElevenLabs API key (TTS) | `""` |
| `SIMLI_API_KEY` | Simli API key (avatar) | `""` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token для auth и платежей | `""` |
| `ELEVENLABS_VOICE_ID` | Voice ID для TTS | `EXAVITQu4vr4xnSDxMaL` |
| `MINUTE_COST_COINS` | Стоимость интервала в монетах | `10` |
| `BILLING_INTERVAL_SECONDS` | Интервал списания (секунды) | `60` |
| `GRACE_PERIOD_SECONDS` | За сколько секунд предупреждать о низком балансе | `30` |
| `CORS_ORIGINS` | Разрешенные CORS origins (JSON list) | `["*"]` |
| `RATE_LIMIT_REQUESTS` | Лимит запросов в окне | `10` |
| `RATE_LIMIT_WINDOW` | Окно rate limit (секунды) | `60` |
| `VAD_ENERGY_THRESHOLD` | Порог энергии для VAD | `0.01` |
| `VAD_SILENCE_DURATION_MS` | Длительность тишины для end-of-utterance (мс) | `800` |

**Пример `.env` файла:**
```env
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://astrologer:password@localhost:5432/ai_astrologer
GROQ_API_KEY=gsk_your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
ELEVENLABS_API_KEY=your_key_here
SIMLI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
MINUTE_COST_COINS=10
BILLING_INTERVAL_SECONDS=60
GRACE_PERIOD_SECONDS=30
CORS_ORIGINS=["http://localhost:5173"]
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (LTS)
- Redis server
- PostgreSQL 16+ (опционально, для persistence)

### Backend

```bash
cd 09_ai_astrologer/backend

# Virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env
cp .env.example .env  # или создать вручную

# Start Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Start PostgreSQL (опционально)
docker run -d --name postgres -p 5432:5432 \
  -e POSTGRES_DB=ai_astrologer \
  -e POSTGRES_USER=astrologer \
  -e POSTGRES_PASSWORD=astrologer_secret \
  postgres:16-alpine

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend: `http://localhost:8000`. API docs: `http://localhost:8000/docs`.

### Frontend

```bash
cd 09_ai_astrologer/frontend

npm install
npm run dev
```

Frontend: `http://localhost:3000`.

### Running Tests

```bash
# Backend
cd 09_ai_astrologer/backend
python -m pytest tests/ -v

# Frontend type check + build
cd 09_ai_astrologer/frontend
npx tsc --noEmit
npm run build
```

---

## Docker Compose (полный стек)

```bash
cd 09_ai_astrologer

# Создать .env с API-ключами (см. выше)
# Запустить все сервисы
docker compose up -d

# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# Redis: localhost:6379
# PostgreSQL: localhost:5432
```

Compose поднимает: Redis, PostgreSQL, Backend (FastAPI), Frontend (nginx + static).
Backend ожидает healthcheck от Redis и Postgres перед стартом.

---

## Production Considerations

### Scaling
- **Gunicorn + Uvicorn workers:** `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`
- **Redis Cluster** для high availability
- **Sticky sessions** для WebSocket за load balancer
- **Billing pub/sub** позволяет горизонтальное масштабирование -- любой pod может обработать reconnect

### Security
- Telegram initData HMAC-SHA256 валидация на каждом защищенном эндпоинте
- First-message auth для WebSocket (не query string)
- Rate limiting через Redis sliding window
- CORS ограничение в production
- Circuit breakers предотвращают cascade failures

### Monitoring
- `GET /metrics` -- Prometheus endpoint
- active_calls, call_duration, billing_events, api_latency, api_errors
- `GET /health` -- для load balancer probes
- Structured logging с Python logging module
