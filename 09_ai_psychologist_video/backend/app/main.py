"""
Основной модуль FastAPI приложения AI Психолог.
Lifespan: инициализация БД, запуск/остановка billing worker.
Middleware: rate limiting (slowapi), structured logging (structlog), Sentry.
"""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text as sa_text

from app.config import settings
from app.models.database import init_db, async_session_factory, async_engine
from app.billing.instance import billing_worker
from app.auth.router import router as auth_router
from app.billing.payment import router as billing_router
from app.billing.promo import router as promo_router
from app.sessions.router import router as sessions_router
from app.call.websocket import websocket_call
from app.call.livekit import router as livekit_router
from app.referral.router import router as referral_router
from app.subscriptions.router import router as subscriptions_router
from app.admin.router import router as admin_router
from app.bot.handlers import router as bot_router


def _configure_structlog() -> None:
    """Настройка структурированного логирования."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL.upper())


def _init_sentry() -> None:
    """Инициализация Sentry SDK, если SENTRY_DSN задан."""
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=0.1,
        )


# Rate limiter - ограничение по IP адресу
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    # Startup
    _configure_structlog()
    _init_sentry()
    await init_db()
    await billing_worker.start()

    logger = structlog.get_logger()
    await logger.ainfo("application_started", version="0.2.0")

    yield

    # Shutdown
    await billing_worker.stop()
    await async_engine.dispose()
    await logger.ainfo("application_stopped")


app = FastAPI(
    title="AI Psychologist Video",
    description="Telegram Mini App - AI Психолог через видеозвонок",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(promo_router)
app.include_router(sessions_router)
app.include_router(livekit_router)
app.include_router(referral_router)
app.include_router(subscriptions_router)
app.include_router(admin_router)
app.include_router(bot_router)

# WebSocket маршрут
app.websocket("/ws/call/{session_id}")(websocket_call)


@app.get("/health")
async def health():
    """Расширенная проверка состояния: БД и Redis."""
    status: dict = {"status": "ok", "db": "unknown", "redis": "unknown"}

    # Проверка подключения к БД
    try:
        async with async_session_factory() as session:
            await session.execute(sa_text("SELECT 1"))
        status["db"] = "ok"
    except Exception:
        status["db"] = "unavailable"

    # Проверка подключения к Redis (graceful degradation)
    try:
        from app.redis_client import get_redis
        r = await get_redis()
        await r.ping()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "unavailable"

    # Общий статус - не fail, просто отмечаем что недоступно
    if status["db"] == "unavailable":
        status["status"] = "degraded"

    return status
