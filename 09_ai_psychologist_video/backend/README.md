# AI Psychologist Video - Backend

FastAPI backend for the AI Psychologist Telegram Mini App.

## Setup

```bash
cd 09_ai_psychologist_video/backend
pip install -r requirements.txt
```

## Run (development)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

Create a `.env` file in the backend directory:

```env
BOT_TOKEN=your_telegram_bot_token
JWT_SECRET=your_secret_key
DATABASE_URL=sqlite+aiosqlite:///./dev.db
REDIS_URL=redis://localhost:6379
RATE_PER_MINUTE=5.0
LLM_API_KEY=
STT_API_KEY=
TTS_API_KEY=
AVATAR_API_KEY=
```

## Architecture

- `app/auth/` - Telegram WebApp auth + JWT
- `app/models/` - SQLAlchemy async models (User, Session, Transaction)
- `app/billing/` - Per-minute billing worker + payment stubs
- `app/call/` - WebSocket handler + AI pipeline stubs
- `app/prompts/` - System prompts for the AI psychologist

## API Endpoints

- `POST /auth/telegram` - Authenticate via Telegram initDataRaw
- `POST /billing/topup` - Top up user balance
- `WS /ws/call/{session_id}?token=JWT` - WebSocket for video call
- `GET /health` - Health check
