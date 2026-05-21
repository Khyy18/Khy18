"""FastAPI приложение для Mini App."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_office.core.database import init_db
from ai_office.api.routes.agents import router as agents_router
from ai_office.api.routes.tasks import router as tasks_router
from ai_office.api.routes.activity import router as activity_router
from ai_office.api.routes.plans import router as plans_router
from ai_office.api.routes.delegations import router as delegations_router
from ai_office.api.routes.services import router as services_router
from ai_office.api.routes.services_extended import router as services_extended_router
from ai_office.api.routes.billing import router as billing_router
from ai_office.api.routes.admin import router as admin_router
from ai_office.api.routes.onboarding import router as onboarding_router
from ai_office.api.middleware import TelegramAuthMiddleware
from ai_office.api.auth import auth_router
from ai_office.api.websocket import websocket_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекст жизненного цикла приложения - создание таблиц при старте."""
    await init_db()
    yield


app = FastAPI(
    title="AI Office API",
    description="API для Telegram Mini App - управление агентами и задачами",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS для Mini App (разрешаем все origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Аутентификация через Telegram initData
app.add_middleware(TelegramAuthMiddleware)

# WebSocket endpoint
app.websocket("/api/ws")(websocket_endpoint)

# Подключение роутеров
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(activity_router)
app.include_router(plans_router)
app.include_router(delegations_router)
app.include_router(services_router)
app.include_router(services_extended_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(onboarding_router)


@app.get("/api/health")
async def health_check():
    """Проверка здоровья сервиса."""
    return {"status": "ok", "service": "ai_office"}
