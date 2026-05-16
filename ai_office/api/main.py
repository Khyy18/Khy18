"""FastAPI приложение для Mini App."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from ai_office.core.config import settings
from ai_office.core.database import init_db
from ai_office.core.logging import setup_logging
from ai_office.api.routes.agents import router as agents_router
from ai_office.api.routes.tasks import router as tasks_router
from ai_office.api.routes.activity import router as activity_router
from ai_office.api.routes.plans import router as plans_router
from ai_office.api.routes.delegations import router as delegations_router
from ai_office.api.routes.usage import router as usage_router
from ai_office.api.routes.metrics import router as metrics_router
from ai_office.api.routes.dashboard import router as dashboard_router
from ai_office.api.routes.templates import router as templates_router
from ai_office.api.routes.feedback import router as feedback_router
from ai_office.api.routes.delegation_trace import router as delegation_trace_router
from ai_office.api.routes.plugins import router as plugins_router
from ai_office.api.routes.admin import router as admin_router
from ai_office.api.middleware import TelegramAuthMiddleware
from ai_office.api.observability import RequestLoggingMiddleware
from ai_office.api.websocket import websocket_endpoint
from ai_office.core.cache import cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекст жизненного цикла приложения - создание таблиц при старте."""
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    await init_db()
    await cache.connect()
    # Seed templates once at startup
    from ai_office.api.routes.templates import seed_templates
    from ai_office.core.database import async_session
    async with async_session() as session:
        await seed_templates(session)
    # Load plugins
    from ai_office.plugins.loader import load_plugins
    load_plugins()
    yield
    await cache.disconnect()


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

# Request logging middleware (before auth)
app.add_middleware(RequestLoggingMiddleware)

# Аутентификация через Telegram initData
app.add_middleware(TelegramAuthMiddleware)

# WebSocket endpoint
app.websocket("/api/ws")(websocket_endpoint)

# Подключение роутеров
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(activity_router)
app.include_router(plans_router)
app.include_router(delegations_router)
app.include_router(usage_router)
app.include_router(metrics_router)
app.include_router(dashboard_router)
app.include_router(templates_router)
app.include_router(feedback_router)
app.include_router(delegation_trace_router)
app.include_router(plugins_router)
app.include_router(admin_router)


@app.get("/api/health")
async def health_check():
    """Проверка здоровья сервиса."""
    return {"status": "ok", "service": "ai_office"}


@app.get("/api/status")
async def system_status(request: Request):
    """Статус системы с информацией о роли пользователя."""
    user_role = getattr(request.state, "user_role", "owner")
    return {
        "status": "ok",
        "service": "ai_office",
        "agents_count": 8,
        "user_role": user_role,
    }
