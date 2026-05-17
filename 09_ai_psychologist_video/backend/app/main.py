"""
Основной модуль FastAPI приложения AI Психолог.
Lifespan: инициализация БД, запуск/остановка billing worker.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db
from app.billing.worker import BillingWorker
from app.auth.router import router as auth_router
from app.billing.payment import router as billing_router
from app.sessions.router import router as sessions_router
from app.call.websocket import websocket_call

billing_worker = BillingWorker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    # Startup
    await init_db()
    await billing_worker.start()
    yield
    # Shutdown
    await billing_worker.stop()


app = FastAPI(
    title="AI Psychologist Video",
    description="Telegram Mini App - AI Психолог через видеозвонок",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS для фронтенда (Vite dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(sessions_router)

# WebSocket маршрут
app.websocket("/ws/call/{session_id}")(websocket_call)


@app.get("/health")
async def health():
    return {"status": "ok"}
