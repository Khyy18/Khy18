# AI-Astrolог: Твой личный разбор по видеосвязи

Telegram Mini App для живых астрологических консультаций с AI-персонажем.
Пользователь вводит дату/время/место рождения, получает натальную карту и начинает голосовой видеозвонок с AI-астрологом "Стеллой" -- харизматичной 22-летней девушкой-блогером, которая разбирает карту в режиме реального времени.

---

## Архитектура

```
+---------------------+           +---------------------+
|   TMA Frontend      |           |   FastAPI Backend   |
|  (React + Vite)     |           |   (Python 3.11)     |
|                     |           |                     |
|  AstroCall UI       +--REST---->+  /api/session/start |
|  Balance display    |           |  /api/balance/topup |
|  User video preview |           |  Natal chart calc   |
|                     |           |  (pyswisseph)       |
|                     +--WS------>+  /ws/call/{id}      |
|                     +--WS------>+  /ws/billing/{id}   |
+---------------------+           +----------+----------+
                                             |
                                             | async
                                             v
                                  +----------+----------+
                                  |     AI Pipeline     |
                                  |                     |
                                  | 1. Groq STT         |
                                  |    (Distil-Whisper) |
                                  | 2. Claude LLM       |
                                  |    (Anthropic API)  |
                                  | 3. ElevenLabs TTS   |
                                  |    (multilingual)   |
                                  | 4. Lip-Sync Avatar  |
                                  |    (Simli/LiveKit)  |
                                  +---------------------+

                                  +---------------------+
                                  |       Redis         |
                                  |  - User balances    |
                                  |  - Session state    |
                                  +---------------------+
```

---

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| Python 3.11 | Runtime |
| FastAPI | HTTP + WebSocket framework |
| Uvicorn | ASGI server |
| pyswisseph | Swiss Ephemeris for natal chart calculation |
| Redis (async) | Balance storage, session state |
| Pydantic v2 | Data validation and settings |
| httpx | Async HTTP client for external APIs |

### Frontend
| Technology | Purpose |
|---|---|
| React 18 | UI framework |
| TypeScript 5 | Type safety |
| Vite 6 | Build tool / dev server |
| TailwindCSS 3 | Utility-first CSS |
| @telegram-apps/sdk-react | Telegram Mini App SDK |

### External APIs
| Service | Role |
|---|---|
| Groq (Distil-Whisper) | Speech-to-Text |
| Anthropic Claude | LLM for astrologer persona |
| ElevenLabs | Text-to-Speech |
| Simli / LiveKit | Lip-sync avatar video (placeholder) |

---

## Модули

### Модуль 1: Natal Chart (Натальная карта)

**Файл:** `backend/app/astro.py`

Рассчитывает полную натальную карту с помощью Swiss Ephemeris (pyswisseph):
- Позиции 10 планет (Солнце, Луна, Меркурий, Венера, Марс, Юпитер, Сатурн, Уран, Нептун, Плутон)
- 12 домов (система Плацидуса)
- Асцендент и MC (Середина Неба)
- Аспекты между планетами (конъюнкция, оппозиция, трин, квадрат, секстиль) с учетом орбисов

Вход: дата, время рождения, широта/долгота места рождения.
Выход: объект `NatalChart` с полным описанием карты.

### Модуль 2: System Prompt Persona (AI-персонаж)

**Файл:** `backend/app/prompts.py`

Формирует системный промпт для Claude, определяющий персонажа "Стеллу":
- 22-летняя девушка-астролог и блогер
- Общается неформально, с молодежным сленгом
- Отвечает 1-3 предложениями (формат голосового сообщения)
- Эмоциональная, позитивная, поддерживающая
- Натальная карта пользователя инжектится в промпт для персонализации

### Модуль 3: Billing / WebSocket (Биллинг)

**Файл:** `backend/app/billing.py`

Система поминутной тарификации через Redis и WebSocket:
- Хранение баланса в Redis (`balance:{user_id}`)
- Background task списывает монеты каждые N секунд (настраивается)
- WebSocket отправляет `BALANCE_UPDATE` после каждого списания
- При нулевом балансе отправляет `TERMINATE_CALL` и завершает сессию
- Поддержка пополнения баланса через REST endpoint

### Модуль 4: Call UI (Интерфейс звонка)

**Файл:** `frontend/src/components/AstroCall.tsx`

React-компонент полноэкранного видеозвонка:
- Видео AI-аватара на весь экран
- Круглое превью камеры пользователя (верхний правый угол)
- Индикатор соединения (зеленый/красный)
- Анимированный статус ("Астролог слушает...", "Советуется со звездами...")
- Кнопки: mute микрофона, завершить звонок, отображение баланса
- Экран "Баланс исчерпан" с кнопкой пополнения
- Поддержка Telegram WebApp API

---

## API Endpoints

### POST /api/session/start

Создает новую сессию: рассчитывает натальную карту, инициализирует AI pipeline.

**Request:**
```json
{
  "user_id": "tg_12345",
  "birth_data": {
    "date": "1995-03-15",
    "time": "14:30",
    "lat": 55.7558,
    "lon": 37.6173,
    "city": "Москва"
  },
  "balance": 100
}
```

**Response:**
```json
{
  "session_id": "uuid-string",
  "natal_chart": {
    "planets": {
      "Sun": { "sign": "Pisces", "degree": "24.51", "house": "10" },
      "Moon": { "sign": "Leo", "degree": "12.33", "house": "3" }
    },
    "houses": { "1": "Gemini", "2": "Cancer" },
    "ascendant": "Gemini",
    "mc": "Pisces",
    "aspects": [
      { "planet1": "Sun", "planet2": "Moon", "aspect_type": "Trine", "orb": "2.18" }
    ]
  },
  "balance": 100
}
```

### GET /api/session/{session_id}/status

Возвращает текущий статус сессии.

**Response:**
```json
{
  "session_id": "uuid-string",
  "status": "active",
  "balance": 80,
  "user_id": "tg_12345"
}
```

Возможные статусы: `idle`, `connecting`, `active`, `ended`.

### POST /api/balance/topup

Пополнение баланса пользователя.

**Request:**
```json
{
  "user_id": "tg_12345",
  "amount": 50
}
```

**Response:**
```json
{
  "user_id": "tg_12345",
  "new_balance": 130
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "ai-astrologer"
}
```

---

## WebSocket Protocol

### WS /ws/call/{session_id}

Двунаправленный канал для обмена аудио/видео данными во время звонка.

**Client -> Server:** Binary audio frames (WebM/Opus)

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

После JSON-сообщения, если `has_audio: true`, сервер отправляет binary frame с MP3-аудио.

### WS /ws/billing/{session_id}

Односторонний канал для уведомлений о биллинге.

**Message types:**

#### BALANCE_UPDATE

Отправляется каждый биллинговый интервал (по умолчанию 60 секунд) после списания.

```json
{
  "event_type": "BALANCE_UPDATE",
  "user_id": "tg_12345",
  "session_id": "uuid-string",
  "amount": 10,
  "balance_after": 80,
  "timestamp": "2024-01-15T12:00:00"
}
```

#### TERMINATE_CALL

Отправляется когда баланс недостаточен для списания. Клиент должен завершить звонок.

```json
{
  "event_type": "TERMINATE_CALL",
  "user_id": "tg_12345",
  "session_id": "uuid-string",
  "amount": 0,
  "balance_after": 5,
  "timestamp": "2024-01-15T12:05:00"
}
```

---

## Environment Variables

Создайте файл `.env` в директории `backend/`:

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `GROQ_API_KEY` | Groq API key for speech-to-text (Distil-Whisper) | `""` |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude LLM | `""` |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for text-to-speech | `""` |
| `SIMLI_API_KEY` | Simli API key for lip-sync avatar | `""` |
| `ELEVENLABS_VOICE_ID` | Voice ID for ElevenLabs TTS | `EXAVITQu4vr4xnSDxMaL` |
| `MINUTE_COST_COINS` | Cost per billing interval in coins | `10` |
| `BILLING_INTERVAL_SECONDS` | Seconds between balance deductions | `60` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON list) | `["*"]` |

**Пример `.env` файла:**
```env
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=gsk_your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
ELEVENLABS_API_KEY=your_key_here
SIMLI_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
MINUTE_COST_COINS=10
BILLING_INTERVAL_SECONDS=60
CORS_ORIGINS=["http://localhost:5173"]
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (LTS recommended)
- Redis server (local or Docker)

### Backend

```bash
cd 09_ai_astrologer/backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (see Environment Variables section)
cp .env.example .env  # or create manually

# Start Redis (via Docker if not installed locally)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd 09_ai_astrologer/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend will be available at `http://localhost:5173`.

### Running Tests

```bash
# Backend tests
cd 09_ai_astrologer/backend
python -m pytest tests/ -v

# Frontend build check
cd 09_ai_astrologer/frontend
npm run build
```

---

## Docker Deployment

### Backend

```bash
cd 09_ai_astrologer/backend

# Build image
docker build -t ai-astrologer-backend .

# Run container
docker run -d \
  --name ai-astrologer \
  -p 8000:8000 \
  -e REDIS_URL=redis://redis:6379/0 \
  -e GROQ_API_KEY=your_key \
  -e ANTHROPIC_API_KEY=your_key \
  -e ELEVENLABS_API_KEY=your_key \
  -e BILLING_INTERVAL_SECONDS=60 \
  -e MINUTE_COST_COINS=10 \
  ai-astrologer-backend
```

### Docker Compose (full stack)

```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - GROQ_API_KEY=${GROQ_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      - SIMLI_API_KEY=${SIMLI_API_KEY}
      - CORS_ORIGINS=["https://your-domain.com"]
    depends_on:
      - redis

  frontend:
    build: ./frontend
    ports:
      - "3000:80"

volumes:
  redis_data:
```

---

## Production Considerations

### Scaling

- **Multiple Uvicorn workers:** Use `gunicorn` with `uvicorn.workers.UvicornWorker` for multi-process deployment:
  ```bash
  gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
  ```
- **Redis Cluster:** For high availability, use Redis Sentinel or Redis Cluster. The app uses simple key-value operations compatible with both modes.
- **WebSocket sticky sessions:** When running behind a load balancer (nginx, HAProxy), enable sticky sessions for WebSocket connections since billing loops are tied to specific server instances.
- **Horizontal scaling:** Move billing state entirely into Redis (pub/sub for billing events) to allow any backend instance to handle reconnects.

### Security

- **Telegram Init Data validation:** Validate `initData` from `@telegram-apps/sdk-react` on the backend to verify user identity.
- **CORS:** Restrict `CORS_ORIGINS` to your Telegram Mini App domain in production.
- **Rate limiting:** Add rate limiting on `/api/session/start` and `/api/balance/topup` to prevent abuse.
- **API keys:** Store all API keys in environment variables or a secrets manager; never commit them to the repository.
- **WebSocket authentication:** Add token-based auth to WebSocket upgrade requests to prevent unauthorized access.
- **Input validation:** Pydantic models enforce strict input validation on all endpoints.

### Monitoring

- **Health endpoint:** `GET /health` for load balancer probes.
- **Structured logging:** Use Python `logging` module (already configured) with JSON formatter for production.
- **Metrics:** Add Prometheus metrics for call duration, billing events, API latency, and WebSocket connection count.
- **Alerts:** Monitor Redis connectivity and external API failures (Groq, Anthropic, ElevenLabs) with circuit breakers.
- **Billing auditing:** Log all billing events to a persistent store for dispute resolution and financial reconciliation.

### Performance

- **Connection pooling:** Use `httpx.AsyncClient` with connection pooling for external API calls in production (avoid creating new clients per request).
- **Audio streaming:** Consider chunked audio streaming instead of full request/response for lower latency.
- **Redis pipeline:** Batch Redis operations where possible to reduce round-trips.
- **CDN:** Serve the frontend build through a CDN (Cloudflare, etc.) for low-latency global access.
